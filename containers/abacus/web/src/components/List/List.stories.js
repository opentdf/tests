import Container from '@/helpers/storybookContainer';
import List from '.';

export default {
  title: 'List',
  component: List,
};

const kas = 'https://kas.domain.tld/';
const actionKey = 'entities-details';
const items = [
  {
    key: 'SI',
    name: 'SI',
    detail: kas,
    actions: [
      {
        key: actionKey,
        children: [
          <a href="javascript;" onClick={() => {}}>
            Entities &amp; details
          </a>,
        ],
      },
    ],
  },
  {
    key: 'TK',
    name: 'TK',
    detail: kas,
    actions: [
      {
        key: actionKey,
        children: [
          <a href="javascript;" onClick={() => {}}>
            Entities &amp; details
          </a>,
        ],
      },
    ],
  },
  {
    key: 'GAMMA ZZYY',
    name: 'GAMMA ZZYY',
    detail: kas,
    actions: [
      {
        key: actionKey,
        children: [
          <a href="javascript;" onClick={() => {}}>
            Entities &amp; details
          </a>,
        ],
      },
    ],
  },
  {
    key: 'GAMMA NEMO',
    name: 'GAMMA NEMO',
    detail: kas,
    actions: [
      {
        key: actionKey,
        children: [
          <a href="javascript;" onClick={() => {}}>
            Entities &amp; details
          </a>,
        ],
      },
    ],
  },
];

export const unorderedList = () => (
  <Container>
    <List>
      {items.map((item) => {
        return (
          <List.Item detail={item.detail} actions={item.actions}>
            {item.name}
          </List.Item>
        );
      })}
    </List>
  </Container>
);

export const orderedList = () => (
  <Container>
    <List isOrdered>
      {items.map((item) => {
        return <List.Item>{item.name}</List.Item>;
      })}
    </List>
  </Container>
);
