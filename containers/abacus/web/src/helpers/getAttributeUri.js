const getUri = ({ ns, attr, val }) => `${ns}/attr/${attr}/value/${val}`;

export default getUri;
