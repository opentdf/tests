import * as React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect } from 'chai';
import App from './App.jsx';

describe('<App>', () => {
  it('renders', () => {
    render(<App />);
    const element = screen.getByText(/object Object/);
    expect(document.body.contains(element)).to.be.ok;
  });

  it('loads files', async () => {
    const user = userEvent.setup();
    const file = new File(['hello, world!'], 'hello.txt', { type: 'text/plain' });
    render(<App />);
    const input = screen.getByLabelText(/select file/i) as HTMLInputElement;
    user.upload(input, file);
    const filenameEl = await screen.findByText(/hello.txt/i);
    expect(document.body.contains(filenameEl)).to.be.ok;
  });

  it('processes files', async () => {
    const user = userEvent.setup();
    const file = new File(['hello, world!'], 'hello.txt', { type: 'text/plain' });
    render(<App />);
    const input = screen.getByLabelText(/select file/i) as HTMLInputElement;
    user.upload(input, file);
    await screen.findByText(/hello.txt/i);
    const processButton = screen.getByText(/process/i) as HTMLInputElement;
    user.click(processButton);
    const el = await screen.findByText(/found/i);
    expect(el.textContent).to.match(/found[:]\s*68/i);
  });
});
