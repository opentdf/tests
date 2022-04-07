import {Select} from "antd";
import {useCallback, useState} from "react";
import {useKeycloak} from "@react-keycloak/web";
import {ENV_REALMS, keycloakConfig} from "../../config";
import {saveNewRealm} from "./utils";
const  {Option} = Select;

export const SelectRealm = ()=> {
    const { keycloak } = useKeycloak();
    const [currentRealm, setRealm] = useState(keycloakConfig.realm);
    const handleChange = useCallback((value) => {
        setRealm(value);
        saveNewRealm(keycloak, value);
    }, [keycloak]);
    const optionList = ENV_REALMS.map(realm => (<Option key={realm.toString()} value={realm}>{realm}</Option>));

    return (
        <>
            {'Realm : '}
            <Select defaultValue={currentRealm} style={{ width: 150 }} onChange={handleChange}>
                {optionList}
            </Select>
        </>
    )
};
