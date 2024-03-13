import React from 'react';
import { useKeycloak } from '@react-keycloak/web';
import useEncrypt from './hooks/useEncrypt';
import useDecrypt from './hooks/useDecrypt';

import Login from './components/login/login'
import './App.css';

function App() {
  const { keycloak, initialized } = useKeycloak();
  const encrypt = useEncrypt(keycloak);
  const decrypt = useDecrypt(keycloak);

  const onClickEncrypt = async () => {
      const encryptedName = await encrypt("Test Message");
      const decryptedText = await decrypt(encryptedName);
  }

  if (!initialized) {
      return <div className="wrapper">Loading...</div>
  }

  return (
    <div className="wrapper">
        <Login keycloak={keycloak} initialized={initialized}/>
        {keycloak.authenticated && (<div>
          <div>Authenticated</div>
          <button onClick={onClickEncrypt}>Test</button>
        </div>)}
        {!keycloak.authenticated && (<>Not Authenticated</>)}
    </div>
  );
}

export default App;
