/* eslint-disable import/no-extraneous-dependencies */
const path = require('path');
const fs = require('fs');
const yaml = require('js-yaml');

const ROOT_DIR = path.resolve(__dirname, '../../../../');
const EAS_OPENAPI = 'eas/openapi.yaml';
const CA_CERT = 'certs/ca.crt';
const CLIENT_CERT = 'certs/Alice_1234.crt';
const CLIENT_KEY = 'certs/Alice_1234.crt';

function getOpenAPISchemas() {
  // Load the OpenApi files
  try {
    return {
      eas: yaml.safeLoad(fs.readFileSync(path.resolve(ROOT_DIR, EAS_OPENAPI), 'utf8')),
    };
  } catch (e) {
    console.error('Could not open EAS and/or KAS OpenAPI files');
    throw e;
  }
}

function getClientCertificates() {
  return {
    clientCert: fs.readFileSync(path.resolve(ROOT_DIR, CLIENT_CERT), 'utf8'),
    clientKey: fs.readFileSync(path.resolve(ROOT_DIR, CLIENT_KEY), 'utf8'),
    caCert: fs.readFileSync(path.resolve(ROOT_DIR, CA_CERT), 'utf8'),
  };
}

module.exports = {
  openApi: getOpenAPISchemas(),
  certs: getClientCertificates(),
};
