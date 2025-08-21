module github.com/opentdf/tests/xtest/sdk/go/server

go 1.22

require (
	github.com/gorilla/mux v1.8.1
	github.com/opentdf/platform/sdk v0.0.0
	github.com/opentdf/platform/service v0.0.0
)

// Use local platform SDK
replace github.com/opentdf/platform/sdk => ../../../../work/platform/sdk
replace github.com/opentdf/platform/service => ../../../../work/platform/service