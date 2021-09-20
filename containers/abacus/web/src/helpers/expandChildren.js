import { Children } from 'react';

/**
 * Expand children for an enhanced component API
 *
 * **NOTE: You must add the `displayName` property to your component or code minification will break this feature.**
 *
 * This utility helps in the process of developing enhanced component APIs where you add specific components as children
 * and not render them with the rest of the children. This is useful to utilize components as flags or distinct structures.
 *
 * @example
 * ```jsx
 * // Given some component implementation
 * <List>
 *   Content after list 1
 *   <List.Item>One</List.Item>
 *   Content after list 2
 *   <List.Item>Two</List.Item>
 *   Content after list 3
 * </List>
 * ```
 *
 * ```jsx
 * // Extract the Items from the children
 * const Item = ({ children }) => (<li>{children}</li>);
 * Item.displayName = 'Item';
 *
 * const List = ({ children }) => {
 *   const [ nextChildren, { Item: itemChildren } ] = expandChildren(children, [ Item ]);
 *   return (
 *     <div>
 *       <ul>{itemChildren}</ul>
 *       {nextChildren}
 *     </div>
 *   );
 * }
 *
 * List.Item = Item;
 * ```
 *
 * ```html
 * <!-- Renders as -->
 * <div>
 *   <ul>
 *     <li>One</li>
 *     <li>Two</li>
 *   </ul>
 *   Content after list 1
 *   Content after list 2
 *   Content after list 3
 * </div>
 * ```
 *
 * @param {array} children children
 * @param {array} childrenToExpand Children which will be ex
 * @returns {[array, object.<string, array.ChildNode>]} Returns an array of children leftover from the expanded children
 */
export default function expandChildren(children, childrenToExpand) {
  const defaultReturn = [children, {}];
  if (!Array.isArray(childrenToExpand)) {
    throw new Error('childrenToExpand must be an array');
  }
  if (!Array.isArray(children) || !children.length || !childrenToExpand.length) {
    return defaultReturn;
  }

  const nextChildren = [];
  const expandedChildren = {};
  Children.forEach(children, (child) => {
    const childType = childrenToExpand.find((model) => {
      return (
        model &&
        model.displayName &&
        child &&
        child.type &&
        child.type.displayName === model.displayName
      );
    });
    if (childType) {
      if (!expandedChildren[childType.displayName]) {
        expandedChildren[childType.displayName] = [];
      }
      expandedChildren[childType.displayName].push(child);
    } else {
      nextChildren.push(child);
    }
  });
  return [nextChildren, expandedChildren];
}
