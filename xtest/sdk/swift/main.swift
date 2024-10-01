import ArgumentParser
                              import Foundation

                              @main
                              struct CLI: ParsableCommand {
                                  @Argument(help: "Operation to perform (encrypt/decrypt)")
                                  var operation: String

                                  @Option(name: .shortAndLong, help: "Output file")
                                  var outputFile: String

                                  @Option(name: .long, help: "Platform URL")
                                  var host: String

                                  @Flag(name: .long, help: "Disable TLS verification")
                                  var tlsNoVerify: Bool = false

                                  @Option(name: .long, help: "Log level")
                                  var logLevel: String = "info"

                                  @Option(name: .long, help: "Client credentials in JSON format")
                                  var withClientCreds: String

                                  @Option(name: .long, help: "TDF type")
                                  var tdfType: String?

                                  @Option(name: .long, help: "MIME type")
                                  var mimeType: String?

                                  @Option(name: .long, help: "Attribute")
                                  var attr: String?

                                  @Argument(help: "Input file")
                                  var inputFile: String

                                  func run() throws {
                                      var args: [String] = [
                                          operation,
                                          "-o", outputFile,
                                          "--host", host,
                                          "--log-level", logLevel,
                                          "--with-client-creds", withClientCreds,
                                      ]

                                      if tlsNoVerify {
                                          args.append("--tls-no-verify")
                                      }

                                      if let tdfType {
                                          args.append(contentsOf: ["--tdf-type", tdfType])
                                      }

                                      if let mimeType {
                                          args.append(contentsOf: ["--mime-type", mimeType])
                                      }

                                      if let attr {
                                          args.append(contentsOf: ["--attr", attr])
                                      }

                                      // Append the input file at the end of arguments
                                      args.append(inputFile)

                                      let cmd = ["./.build/release/cli"] + args

                                      print(cmd)
                                      runCommand(cmd)
                                  }

                                  func runCommand(_ command: [String]) {
                                      let process = Process()
                                      process.executableURL = URL(fileURLWithPath: command[0])
                                      process.arguments = Array(command.dropFirst())

                                      do {
                                          try process.run()
                                          process.waitUntilExit()

                                          if process.terminationStatus != 0 {
                                              Foundation.exit(1)
                                          }

                                          if operation == "encrypt", FileManager.default.fileExists(atPath: "\(outputFile).tdf") {
                                              try FileManager.default.moveItem(atPath: "\(outputFile).tdf", toPath: outputFile)
                                          }
                                      } catch {
                                          print("Error: \(error)")
                                          Foundation.exit(1)
                                      }
                                  }
                              }
