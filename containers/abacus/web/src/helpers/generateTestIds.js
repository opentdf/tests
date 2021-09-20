/**
 * Generate an object of test ids
 *
 * This is very useful in tests and will have other useful purposes during building such as generating unique ids.
 *
 * @param {*} namespace namespace of the test id
 * @param {*} ids array of ids to generate
 * @param {*} options options
 * @param {string} options.containerKey the key for the container
 */
export default function generateTestIds(namespace, ids = [], options = {}) {
  if (!namespace) {
    throw new Error('namespace required for test ids');
  }

  const { containerKey } = { containerKey: '_', ...options };
  return ids.reduce(
    (nextIds, id) => {
      return { ...nextIds, [id]: `${namespace}-${id}` };
    },
    { [containerKey]: namespace }
  );
}
