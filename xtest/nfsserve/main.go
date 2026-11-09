// Command nfsserve exports one read-only file over NFSv3 on loopback. Every
// NFS READ becomes a Range GET to an HTTP server (xtest/rangeserve.py), so the
// retention plan and request log live there, not here.
//
// A GET answered 410 Gone (a dropped extent) reads as filler rather than an
// error: the kernel rounds application reads out to whole NFS READs, and an
// error there would fail the application's read of kept bytes too.
//
// Prints the listening port on stdout, then serves until stdin closes.
package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"path"
	"strings"
	"time"

	billy "github.com/go-git/go-billy/v5"
	"github.com/go-git/go-billy/v5/memfs"
	nfs "github.com/willscott/go-nfs"
	nfshelper "github.com/willscott/go-nfs/helpers"
)

// filler must match FILLER in xtest/nfsmount.py.
const filler = "DROPPED!"

var client = &http.Client{
	Timeout:   time.Minute,
	Transport: &http.Transport{MaxIdleConnsPerHost: 16},
}

type remote struct {
	url  string
	name string
	size int64
}

func (r *remote) Name() string       { return r.name }
func (r *remote) Size() int64        { return r.size }
func (r *remote) Mode() os.FileMode  { return 0o444 }
func (r *remote) ModTime() time.Time { return time.Unix(0, 0) }
func (r *remote) IsDir() bool        { return false }
func (r *remote) Sys() any           { return nil }

// ReadAt fetches [off, off+len(p)) with one Range GET.
func (r *remote) ReadAt(p []byte, off int64) (int, error) {
	if off >= r.size {
		return 0, io.EOF
	}
	n := int(min(int64(len(p)), r.size-off))
	if n == 0 {
		return 0, nil
	}
	req, err := http.NewRequest(http.MethodGet, r.url, nil)
	if err != nil {
		return 0, err
	}
	rng := fmt.Sprintf("bytes=%d-%d", off, off+int64(n)-1)
	req.Header.Set("Range", rng)
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("GET %s: %v", rng, err)
		return 0, err
	}
	defer resp.Body.Close()
	switch resp.StatusCode {
	case http.StatusPartialContent:
		if _, err := io.ReadFull(resp.Body, p[:n]); err != nil {
			log.Printf("GET %s: %v", rng, err)
			return 0, err
		}
	case http.StatusGone:
		_, _ = io.Copy(io.Discard, resp.Body)
		for i := range p[:n] {
			p[i] = filler[(off+int64(i))%int64(len(filler))]
		}
		log.Printf("filler %s", rng)
	default:
		err := fmt.Errorf("GET %s: %s", rng, resp.Status)
		log.Print(err)
		return 0, err
	}
	if off+int64(n) == r.size {
		return n, io.EOF
	}
	return n, nil
}

// handle is an open file; go-nfs only reads through ReadAt.
type handle struct {
	*remote
	pos int64
}

func (h *handle) Read(p []byte) (int, error) {
	n, err := h.ReadAt(p, h.pos)
	h.pos += int64(n)
	return n, err
}

func (h *handle) Seek(o int64, whence int) (int64, error) {
	switch whence {
	case io.SeekStart:
	case io.SeekCurrent:
		o += h.pos
	case io.SeekEnd:
		o += h.size
	default:
		return 0, os.ErrInvalid
	}
	h.pos = o
	return o, nil
}

func (*handle) Write([]byte) (int, error) { return 0, os.ErrPermission }
func (*handle) Truncate(int64) error      { return os.ErrPermission }
func (*handle) Close() error              { return nil }
func (*handle) Lock() error               { return nil }
func (*handle) Unlock() error             { return nil }

// fsys is an empty read-only directory holding the one remote file.
type fsys struct {
	billy.Filesystem
	file *remote
}

func (f fsys) is(p string) bool { return strings.TrimPrefix(p, "/") == f.file.name }

func (f fsys) Capabilities() billy.Capability {
	return billy.ReadCapability | billy.SeekCapability
}

func (f fsys) Stat(p string) (os.FileInfo, error) {
	if f.is(p) {
		return f.file, nil
	}
	return f.Filesystem.Stat(p)
}

func (f fsys) Lstat(p string) (os.FileInfo, error) { return f.Stat(p) }

func (f fsys) Open(p string) (billy.File, error) { return f.OpenFile(p, os.O_RDONLY, 0) }

func (f fsys) OpenFile(p string, flag int, perm os.FileMode) (billy.File, error) {
	if !f.is(p) {
		return nil, os.ErrNotExist
	}
	if flag&(os.O_WRONLY|os.O_RDWR) != 0 {
		return nil, os.ErrPermission
	}
	return &handle{remote: f.file}, nil
}

func (f fsys) ReadDir(p string) ([]os.FileInfo, error) {
	if strings.Trim(p, "/.") != "" {
		return nil, os.ErrNotExist
	}
	return []os.FileInfo{f.file}, nil
}

type readOnly struct{ nfs.Handler }

func (readOnly) Change(billy.Filesystem) billy.Change { return nil }

func open(raw string) (*remote, error) {
	u, err := url.Parse(raw)
	if err != nil {
		return nil, err
	}
	resp, err := client.Head(raw)
	if err != nil {
		return nil, err
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK || resp.ContentLength < 0 {
		return nil, fmt.Errorf("HEAD %s: %s, length %d", raw, resp.Status, resp.ContentLength)
	}
	name := path.Base(u.Path)
	if name == "/" || name == "." {
		return nil, errors.New("url has no file name")
	}
	return &remote{url: raw, name: name, size: resp.ContentLength}, nil
}

func main() {
	src := flag.String("url", "", "HTTP URL of the file to export")
	flag.Parse()
	log.SetPrefix("nfsserve: ")
	file, err := open(*src)
	if err != nil {
		log.Fatal(err)
	}
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(l.Addr().(*net.TCPAddr).Port)
	// Exit when the parent goes, even if it is killed.
	go func() {
		_, _ = io.Copy(io.Discard, os.Stdin)
		os.Exit(0)
	}()
	h := nfshelper.NewCachingHandler(readOnly{nfshelper.NewNullAuthHandler(fsys{memfs.New(), file})}, 1024)
	log.Fatal(nfs.Serve(l, h))
}
