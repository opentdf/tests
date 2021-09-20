import { useEffect, useState } from 'react';

export default (entityMap, attributeRules) => {
  const [rulesToAssign, setRulesToAssign] = useState([]);

  useEffect(() => {
    const processOrderProp = ({ order, name, ...rest }) => {
      const filteredOrder = order.filter(
        (val) => !entityMap[name] || !entityMap[name].order.includes(val)
      );
      const filteredOutCount = order.length - filteredOrder.length;

      return {
        ...rest,
        name,
        order: filteredOrder,
        filteredOutCount,
      };
    };

    if (!attributeRules || !entityMap) {
      setRulesToAssign([]);
    } else {
      setRulesToAssign(attributeRules.map(processOrderProp));
    }
  }, [entityMap, attributeRules]);

  return rulesToAssign;
};
