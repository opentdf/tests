import Container from '@/helpers/storybookContainer';
import DescriptionTable from '.';

export default {
  title: 'Description Table',
  component: DescriptionTable,
};

export const Table = () => (
  <Container>
    <DescriptionTable
      properties={[
        {
          name: 'Prop1',
          value: 'somevalue1',
        },
        {
          name: 'Prop2',
          value: 'somevalue2',
        },
        {
          name: 'Prop3',
          value: 'somevalue3',
        },
      ]}
    />
  </Container>
);
