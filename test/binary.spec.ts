import { expect } from 'chai';
import { Binary } from '../src/binary';

describe('Binary', () => {
  describe('factory methods', () => {
    it('#fromArrayBuffer', () => {
      const arrayBuffer = Uint8Array.from([97, 98, 99]).buffer;
      const bin = Binary.fromArrayBuffer(arrayBuffer);
      expect(bin.asArrayBuffer()).to.eql(Uint8Array.from([97, 98, 99]).buffer);
      expect(bin.asBuffer()).to.eql(Buffer.from([97, 98, 99]));
      expect(bin.asByteArray()).to.eql([97, 98, 99]);
      expect(bin.asString()).to.eql('abc');
      expect(bin.length()).to.eql(3);
      expect(bin.isArrayBuffer()).to.be.true;
      expect(bin.isBuffer()).to.be.false;
      expect(bin.isByteArray()).to.be.false;
      expect(bin.isString()).to.be.false;
    });

    it('#fromBuffer', () => {
      const buffer = Buffer.from([97, 98, 99]);
      const bin = Binary.fromBuffer(buffer);
      expect(bin.asArrayBuffer()).to.eql(Uint8Array.from([97, 98, 99]).buffer);
      expect(bin.asBuffer()).to.eql(Buffer.from([97, 98, 99]));
      expect(bin.asByteArray()).to.eql([97, 98, 99]);
      expect(bin.asString()).to.eql('abc');
      expect(bin.length()).to.eql(3);
      expect(bin.isArrayBuffer()).to.be.false;
      expect(bin.isBuffer()).to.be.true;
      expect(bin.isByteArray()).to.be.false;
      expect(bin.isString()).to.be.false;
    });

    it('#fromByteArray', () => {
      const byteArray = [97, 98, 99];
      const bin = Binary.fromByteArray(byteArray);
      expect(bin.asArrayBuffer()).to.eql(Uint8Array.from([97, 98, 99]).buffer);
      expect(bin.asBuffer()).to.eql(Buffer.from([97, 98, 99]));
      expect(bin.asByteArray()).to.eql([97, 98, 99]);
      expect(bin.asString()).to.eql('abc');
      expect(bin.length()).to.eql(3);
      expect(bin.isArrayBuffer()).to.be.false;
      expect(bin.isBuffer()).to.be.false;
      expect(bin.isByteArray()).to.be.true;
      expect(bin.isString()).to.be.false;
    });

    it('#fromString', () => {
      const bin = Binary.fromString('abc');
      expect(bin.asArrayBuffer()).to.eql(Uint8Array.from([97, 98, 99]).buffer);
      expect(bin.asBuffer()).to.eql(Buffer.from([97, 98, 99]));
      expect(bin.asByteArray()).to.eql([97, 98, 99]);
      expect(bin.asString()).to.eql('abc');
      expect(bin.length()).to.eql(3);
      expect(bin.isArrayBuffer()).to.be.false;
      expect(bin.isBuffer()).to.be.false;
      expect(bin.isByteArray()).to.be.false;
      expect(bin.isString()).to.be.true;
    });
  });

  describe('binary::unicode', () => {
    it('works with a byteArray and unicode string', () => {
      // TODO(PLAT-1106): byteArray here is utf-8 encoded. WTF.
      const byteArray = [227, 131, 145, 227, 130, 185, 227, 131, 175, 227, 131, 188, 227, 131, 137];
      const bin = Binary.fromByteArray(byteArray);
      const buffer = bin.asArrayBuffer();
      const otherBin = Binary.fromArrayBuffer(buffer);
      expect(otherBin.asString()).to.eql('パスワード');
    });
    it('works with an arrayBuffer unicode', () => {
      const byteArray = [227, 131, 145, 227, 130, 185, 227, 131, 175, 227, 131, 188, 227, 131, 137];
      const buffer = Buffer.from(byteArray);
      const bin = Binary.fromBuffer(buffer);

      const actualBuffer = bin.asArrayBuffer();
      const bufferView = new Uint8Array(actualBuffer);
      const otherBin = Binary.fromArrayBuffer(actualBuffer);
      // Check that the lengths match
      expect(bufferView.length).to.eql(byteArray.length);
      // TODO(PLAT-1106) Note that some asString methods use `utf-8`
      // others use latin-1 (ascii/binary). This results in surprising behavior!
      // Do we rely in this?
      expect(otherBin.asString()).to.eql('パスワード');
    });
  });
});
