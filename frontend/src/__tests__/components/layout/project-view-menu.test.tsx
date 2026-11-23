// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { fireEvent, render, screen } from '@testing-library/react';
import { act } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProjectXiahuaMenu } from '@/components/layout/project-header-navigation';
import { FREEZONE_VIEW_MODE_KEY, resetFreezoneViewMode, useFreezoneViewMode } from '@/features/freezone/useFreezoneViewMode';

const location = vi.hoisted(() => ({ pathname: '/projects/demo/freezone' }));
const mocks = vi.hoisted(() => ({
  contentLanguage: 'id' as string,
  updateProjectMutate: vi.fn(),
}));
vi.mock('@tanstack/react-router', () => ({
  Link: () => null,
  useNavigate: () => vi.fn(),
  useRouterState: ({ select }: { select: (state: { location: typeof location }) => unknown }) => select({ location }),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => ({
    'freezone.viewMode.label': '画布视图切换',
    'freezone.viewMode.workflow': '工作流',
    'freezone.viewMode.board': '故事板',
    'ingest.contentLanguage': 'Narration Language',
    'ingest.contentLanguages.id': 'Indonesian',
    'ingest.contentLanguages.en': 'English',
    'ingest.contentLanguages.zh': 'Mandarin',
  })[key] ?? key }),
}));
vi.mock('@/lib/queries/projects', () => ({
  useProject: () => ({
    data: { ok: true, data: { content_language: mocks.contentLanguage } },
  }),
  useUpdateProject: () => ({
    mutate: mocks.updateProjectMutate,
    isPending: false,
  }),
}));
vi.mock('@/components/ui/select', async () => {
  const React = await import('react');
  type SelectContextValue = {
    value?: string;
    onValueChange?: (value: string) => void;
  };
  const SelectContext = React.createContext<SelectContextValue>({});

  return {
    Select: ({
      value,
      onValueChange,
      children,
    }: {
      value?: string;
      onValueChange?: (value: string) => void;
      children: React.ReactNode;
    }) => (
      <SelectContext.Provider value={{ value, onValueChange }}>
        <div>{children}</div>
      </SelectContext.Provider>
    ),
    SelectTrigger: ({ children, ...props }: { children: React.ReactNode }) => (
      <div {...props}>{children}</div>
    ),
    SelectValue: ({
      children,
      placeholder,
    }: {
      children?: ((value: string) => React.ReactNode) | React.ReactNode;
      placeholder?: React.ReactNode;
    }) => {
      const ctx = React.useContext(SelectContext);
      if (typeof children === 'function') {
        return <span>{ctx.value ? children(ctx.value) : placeholder}</span>;
      }
      return <span>{children ?? placeholder}</span>;
    },
    SelectContent: ({ children }: { children: React.ReactNode }) => (
      <div>{children}</div>
    ),
    SelectItem: ({
      value,
      children,
    }: {
      value: string;
      children: React.ReactNode;
    }) => {
      const ctx = React.useContext(SelectContext);
      return (
        <button
          type="button"
          role="option"
          onClick={() => ctx.onValueChange?.(value)}
        >
          {children}
        </button>
      );
    },
  };
});

function Workspace() {
  const [mode, setMode] = useFreezoneViewMode();
  return <><output data-testid="view">{mode}</output><button onClick={() => setMode('workflow')}>定位到工作流</button></>;
}

describe('project canvas view menu', () => {
  beforeEach(() => {
    location.pathname = '/projects/demo/freezone';
    mocks.contentLanguage = 'id';
    mocks.updateProjectMutate.mockClear();
    const { unmount } = render(<Workspace />);
    act(() => fireEvent.click(screen.getByText('定位到工作流')));
    unmount();
    localStorage.clear();
  });

  it('shares the selected view with the workspace and persists it', () => {
    render(<><ProjectXiahuaMenu project="demo" /><Workspace /></>);
    fireEvent.click(screen.getByRole('tab', { name: '故事板' }));
    expect(screen.getByTestId('view')).toHaveTextContent('board');
    expect(screen.getByRole('tab', { name: '故事板' })).toHaveAttribute('aria-selected', 'true');
    expect(localStorage.getItem(FREEZONE_VIEW_MODE_KEY)).toBe('board');

    fireEvent.click(screen.getByText('定位到工作流'));
    expect(screen.getByRole('tab', { name: '工作流' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('view')).toHaveTextContent('workflow');
  });

  it('resets the live menu, workspace and stored mode on project-folder entry', () => {
    render(<><ProjectXiahuaMenu project="demo" /><Workspace /></>);
    fireEvent.click(screen.getByRole('tab', { name: '故事板' }));
    expect(screen.getByTestId('view')).toHaveTextContent('board');
    act(() => resetFreezoneViewMode());
    expect(screen.getByTestId('view')).toHaveTextContent('workflow');
    expect(screen.getByRole('tab', { name: '工作流' })).toHaveAttribute('aria-selected', 'true');
    expect(localStorage.getItem(FREEZONE_VIEW_MODE_KEY)).toBe('workflow');
  });

  it('supports keyboard selection and only appears under XiaHua', () => {
    const { rerender } = render(<ProjectXiahuaMenu project="demo" />);
    const workflow = screen.getByRole('tab', { name: '工作流' });
    workflow.focus();
    fireEvent.keyDown(workflow, { key: 'End' });
    const board = screen.getByRole('tab', { name: '故事板' });
    expect(board).toHaveFocus();
    expect(board).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(board, { key: 'ArrowLeft' });
    expect(workflow).toHaveFocus();
    expect(workflow).toHaveAttribute('aria-selected', 'true');

    location.pathname = '/projects/demo/ingest';
    rerender(<ProjectXiahuaMenu project="demo" />);
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });

  it('shows the project narration language and saves a new choice', () => {
    const { container } = render(<ProjectXiahuaMenu project="demo" />);
    // Current language (id) is shown in the picker trigger.
    const trigger = container.querySelector('[aria-label="Narration Language"]');
    expect(trigger).not.toBeNull();
    expect(trigger?.textContent).toContain('Indonesian');
    // All three choices are offered; picking English persists it.
    fireEvent.click(screen.getByRole('option', { name: 'English' }));
    expect(mocks.updateProjectMutate).toHaveBeenCalledWith({ content_language: 'en' });
    expect(mocks.updateProjectMutate).toHaveBeenCalledTimes(1);
  });

  it('shows the stored language instead of the Indonesian default', () => {
    mocks.contentLanguage = 'en';
    const { container } = render(<ProjectXiahuaMenu project="demo" />);
    const trigger = container.querySelector('[aria-label="Narration Language"]');
    expect(trigger).not.toBeNull();
    expect(trigger?.textContent).toContain('English');
  });
});
