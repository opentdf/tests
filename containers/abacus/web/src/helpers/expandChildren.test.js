import { Component } from 'react';
import { expandChildren } from '@/helpers';

function ExpandChild() {}
ExpandChild.displayName = 'ExpandChild';

test('should return an errors', () => {
  expect(() => expandChildren()).toThrowError();
  expect(() => expandChildren([], undefined)).toThrowError();
  expect(() => expandChildren([], {})).toThrowError();
});

test('should return all children', () => {
  const ChildOne = <Component />;
  const ChildTwo = <Component />;
  expect(expandChildren([], [])).toEqual([[], {}]);
  expect(expandChildren([ChildOne, ChildTwo], [])).toEqual([[ChildOne, ChildTwo], {}]);
});

test('should expand one child', () => {
  const ChildOne = <Component />;
  const ChildTwo = <ExpandChild />;
  expect(expandChildren([ChildOne, ChildTwo], [ExpandChild])).toEqual([
    [ChildOne],
    { ExpandChild: [ChildTwo] },
  ]);
});

test('should expand all children', () => {
  const ChildOne = <ExpandChild />;
  const ChildTwo = <ExpandChild />;
  expect(expandChildren([ChildOne, ChildTwo], [ExpandChild])).toEqual([
    [],
    { ExpandChild: [ChildOne, ChildTwo] },
  ]);
});

test('should not expand children that do not have a displayName property', () => {
  const ChildOne = <ExpandChild />;
  const ChildTwo = <Component />;
  expect(expandChildren([ChildOne, ChildTwo], [ExpandChild, Component])).toEqual([
    [ChildTwo],
    { ExpandChild: [ChildOne] },
  ]);
});
