// eslint-disable-next-line import/no-extraneous-dependencies
import { withKnobs, boolean } from '@storybook/addon-knobs';

import { Table, TBody, TD, TH, THead, TR } from '.';

export default {
  title: 'Table',
  decorators: [withKnobs],
};

const rowData = {
  cn: 'Common name',
  email: 'email@domain.tld',
  type: 'Person',
  dn: 'Distinguished Name ',
  // eslint-disable-next-line jsx-a11y/anchor-is-valid
  actions: <a href="#">Remove entity from attribute</a>,
};

const data = new Array(9).fill(rowData);

export const DefaultTable = () => (
  <div style={{ width: '1024px' }}>
    <Table>
      {boolean('Headless', false) ? null : (
        <THead>
          <TR>
            <TH>Common Name</TH>
            <TH>Email</TH>
            <TH>Type</TH>
            <TH>Distinguished Name</TH>
            <TH align="right">Actions</TH>
          </TR>
        </THead>
      )}
      <TBody>
        {data.map((row, i) => (
          // eslint-disable-next-line react/no-array-index-key
          <TR key={i}>
            <TD>{row.cn}</TD>
            <TD>{row.email}</TD>
            <TD>{row.type}</TD>
            <TD>{row.dn}</TD>
            <TD align="right">{row.actions}</TD>
          </TR>
        ))}
        {boolean('Removed entity', false) && (
          <TR disabled>
            <TD>
              <span style={{ textDecoration: 'line-through' }}>{rowData.cn}</span>
            </TD>
            <TD>
              <span style={{ textDecoration: 'line-through' }}>{rowData.email}</span>
            </TD>
            <TD>
              <span style={{ textDecoration: 'line-through' }}>{rowData.type}</span>
            </TD>
            <TD>
              <span style={{ textDecoration: 'line-through' }}>{rowData.dn}</span>
            </TD>
            <TD align="right">
              {/* eslint-disable-next-line jsx-a11y/anchor-is-valid */}
              <a href="#" style={{ textDecoration: 'line-through' }}>
                Restore
              </a>
            </TD>
          </TR>
        )}
        {boolean('"Assign entity to attribute" cta', false) && (
          <TR isBordered>
            <TD colSpan={5}>
              <div style={{ fontSize: '13px', textAlign: 'center' }}>
                {/* eslint-disable-next-line jsx-a11y/anchor-is-valid */}
                <a
                  style={{
                    fontSize: '13px',
                  }}
                  href="#"
                >
                  + Assign entity to attribute
                </a>
              </div>
            </TD>
          </TR>
        )}
      </TBody>
    </Table>
  </div>
);
