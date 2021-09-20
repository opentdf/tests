/**
 * Decorates object in array, that matches specific id
 * @param idKey {String} - id key of object by which comparison is made
 * @param idValue {String} - id value of key by which comparison is made
 * @param arr {Array} - array of objects
 * @param decoration {Object} - object that decorates element of array that matched
 * @returns {Array} array unchanged or with switched decorated object or arr
 */
export default ({ idKey, idValue, arr, decoration }) => {
  const i = arr.findIndex((item) => item[idKey] === idValue);
  if (arr[i]) {
    const newArr = [...arr];
    newArr.splice(i, 1, { ...arr[i], ...decoration });
    return newArr;
  }
  return arr;
};
