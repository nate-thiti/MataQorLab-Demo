import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import ChatBranchSelector, { branchDisplayLabel } from './ChatBranchSelector';

vi.mock('../../components/icons', () => ({
  Check: () => React.createElement('span', null, 'check'),
  ChevronDown: () => React.createElement('span', null, 'down'),
  GitBranch: () => React.createElement('span', null, 'branch'),
}));

describe('ChatBranchSelector', () => {
  const branches = [
    { id: 'root', is_root: true, branch_index: 1, title: 'Main' },
    { id: 'edit', branch_index: 2, title: 'แก้ไขคำถาม' },
  ];

  it('formats root and edited branch labels', () => {
    expect(branchDisplayLabel(branches[0], false)).toBe('หลัก');
    expect(branchDisplayLabel(branches[1], false)).toBe('2. แก้ไขคำถาม');
  });

  it('uses the same compact toolbar height instead of a native select', () => {
    const html = renderToStaticMarkup(
      React.createElement(ChatBranchSelector, {
        branches,
        activeBranchId: 'edit',
        onSwitch: vi.fn(),
      }),
    );

    expect(html).toContain('h-9');
    expect(html).toContain('2. แก้ไขคำถาม');
    expect(html).not.toContain('<select');
  });
});
