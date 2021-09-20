import { useState, useEffect } from 'react';

export default function useNsAttrValMap(attrArr, deletedArr) {
  const [map, setMap] = useState({});

  useEffect(() => {
    const newMap = {};

    const fillMap = (url) => {
      const [attr] = url.match(/(?<=\/attr\/)(.*?)(?=\/value\/)/g);
      const [value] = url.match(/(?<=\/value\/)(.*?)+/g);
      const [ns] = url.match(/(.*?)(?=\/attr\/)/g);
      if (!newMap[ns]) {
        newMap[ns] = {};
      }
      if (!newMap[ns][attr]) {
        newMap[ns][attr] = { order: [], authorityNamespace: ns };
      }
      newMap[ns][attr].order.push(value);
    };

    if (attrArr) {
      attrArr.forEach(fillMap);
    }
    if (deletedArr) {
      deletedArr.forEach(fillMap);
    }
    setMap(newMap);
  }, [attrArr, deletedArr]);

  return map;
}
