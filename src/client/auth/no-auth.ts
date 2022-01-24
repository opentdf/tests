import AuthProvider from './provider';

/**
 * AuthProvider that doesn't add anything for auth. Useful for inabox testing.
 */
class NoAuthProvider extends AuthProvider {
  override async injectAuth() {
    // ignored
  }
}

export default NoAuthProvider;
