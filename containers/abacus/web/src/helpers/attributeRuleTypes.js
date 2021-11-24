export const RuleAccessType = {
  PERMISSIVE: 'anyOf',
  RESTRICTIVE: 'allOf',
  HIERARCHICAL: 'hierarchy',
};

export const RuleAccessTypeDescription = {
  [RuleAccessType.PERMISSIVE]: () => (
    <span>
      {'Entities must have '}
      <b>any of</b>
      {' the same attribute values as data.'}
    </span>
  ),
  [RuleAccessType.RESTRICTIVE]: () => (
    <span>
      {'Entities must have at least '}
      <b>all of</b>
      {' the same attribute values as data.'}
    </span>
  ),
  [RuleAccessType.HIERARCHICAL]: () => (
    <span>
      {'Entities must be '}
      <b>higher than or equal to</b>
      {' data in a hierarchy of attribute values.'}
    </span>
  ),
};
