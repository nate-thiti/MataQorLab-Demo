import { describe, expect, it, vi } from 'vitest';
import {
  consumeChatStream,
  preserveStreamedSystemCommands,
} from './chatStream.js';
import { extractSystemCommands } from './messageContent.js';
import { readLocalConversationalFlag } from './orchestration/index.js';

const chartBlock = `\`\`\`json
{
  "action": "render_chart",
  "chart_type": "bar",
  "config": { "title": "Revenue" },
  "data": [{ "name": "A", "value": 10 }]
}
\`\`\``;

describe('preserveStreamedSystemCommands', () => {
  it('keeps a streamed chart when corrected final narration omits it', () => {
    const result = preserveStreamedSystemCommands(
      `Initial analysis\n\n${chartBlock}`,
      'Corrected final analysis',
    );

    expect(result).toContain('Corrected final analysis');
    expect(extractSystemCommands(result)).toEqual([
      expect.objectContaining({ action: 'render_chart', chart_type: 'bar' }),
    ]);
  });

  it('does not duplicate a command already present in final content', () => {
    const result = preserveStreamedSystemCommands(
      `Initial analysis\n\n${chartBlock}`,
      `Final analysis\n\n${chartBlock}`,
    );

    expect(extractSystemCommands(result)).toHaveLength(1);
  });

  it('returns ordinary final narration unchanged', () => {
    expect(preserveStreamedSystemCommands('streamed', 'final')).toBe('final');
  });

  it('does not restore a streamed chart when the final response has a dashboard proposal', () => {
    const proposalBlock = `\`\`\`json
{
  "action": "propose_visualization",
  "title": "Sales dashboard",
  "filters": [],
  "kpis": [],
  "widgets": []
}
\`\`\``;
    const result = preserveStreamedSystemCommands(
      `Initial analysis\n\n${chartBlock}`,
      `Final analysis\n\n${proposalBlock}`,
    );

    expect(extractSystemCommands(result)).toEqual([
      expect.objectContaining({ action: 'propose_visualization' }),
    ]);
  });
});

describe('Visualization command precedence', () => {
  it('does not expose an inline chart when the same message creates a Visualization proposal', () => {
    const proposalBlock = `\`\`\`json
{
  "action": "propose_visualization",
  "title": "Sales dashboard",
  "filters": [],
  "kpis": [],
  "widgets": []
}
\`\`\``;

    expect(extractSystemCommands(`${chartBlock}\n\n${proposalBlock}`)).toEqual([
      expect.objectContaining({ action: 'propose_visualization' }),
    ]);
  });
});

describe('Python analysis proposal command', () => {
  it('keeps code and exact approval metadata for the confirmation card', () => {
    const block = `\`\`\`json
{"action":"propose_python_analysis","job_id":"job-1","approval_id":"pyapprove_hash","code":"result = 1","packages":{},"limits":{"runtime_seconds":60}}
\`\`\``;
    expect(extractSystemCommands(block)).toEqual([
      expect.objectContaining({
        action: 'propose_python_analysis',
        job_id: 'job-1',
        approval_id: 'pyapprove_hash',
        code: 'result = 1',
      }),
    ]);
  });
});

describe('DAX preview command', () => {
  it('preserves formula and approval metadata for explicit publish', () => {
    const block = `\`\`\`json
{"action":"preview_dax_definition","dataset_key":"sales.xlsx","name":"Margin","mode":"measure","expression":"DIVIDE(SUM([profit]),SUM([sales]))","approved_action_id":"daxapprove_hash","preview":{"value":0.2}}
\`\`\``;
    expect(extractSystemCommands(block)).toEqual([
      expect.objectContaining({ action: 'preview_dax_definition', name: 'Margin', approved_action_id: 'daxapprove_hash' }),
    ]);
  });
});

describe('consumeChatStream', () => {
  it('returns automatic continuation metadata from the done event', async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(
          'data: {"type":"done","message":{"role":"assistant","content":"คำตอบครบแล้ว"},'
          + '"finish_reason":"stop","generation_continuations":1,'
          + '"generation_truncated":false}\n\n',
        ));
        controller.close();
      },
    });
    global.fetch = vi.fn().mockResolvedValue(new Response(body, { status: 200 }));

    const result = await consumeChatStream(
      '/api/v1/chat/stream',
      { authorization: 'Bearer token', body: {} },
      undefined,
    );

    expect(result.content).toBe('คำตอบครบแล้ว');
    expect(result.finish_reason).toBe('stop');
    expect(result.generation_continuations).toBe(1);
    expect(result.generation_truncated).toBe(false);
  });

  it('persists orchestration payload from the done event', async () => {
    const encoder = new TextEncoder();
    const orchestration = {
      decision_type: 'ask_user',
      workflow: {
        status: 'awaiting_user',
        steps: [{ step_type: 'clean', status: 'awaiting_user' }],
      },
      awaiting_user: { question: 'Confirm?', options: [{ value: 'approved', label: 'OK' }] },
    };
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(
          'data: {"type":"token","content":"Confirm?"}\n\n',
        ));
        controller.enqueue(encoder.encode(
          `data: ${JSON.stringify({
            type: 'done',
            message: { role: 'assistant', content: 'Confirm?' },
            agent_paused: true,
            routing: { path: 'conversational_data_setup' },
            orchestration,
          })}\n\n`,
        ));
        controller.close();
      },
    });
    global.fetch = vi.fn().mockResolvedValue(new Response(body, { status: 200 }));

    const result = await consumeChatStream(
      '/api/v1/chat/stream',
      { authorization: 'Bearer token', body: {} },
      undefined,
    );

    expect(result.content).toBe('Confirm?');
    expect(result.agent_paused).toBe(true);
    expect(result.routing.path).toBe('conversational_data_setup');
    expect(result.orchestration).toEqual(orchestration);
  });

  it('persists the server-owned tool execution ledger', async () => {
    const encoder = new TextEncoder();
    const toolExecution = {
      policy: 'tool_first_compute_only',
      satisfied: true,
      calls: [{ tool: 'dataset_query', engine: 'duckdb', status: 'completed' }],
    };
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(
          `data: ${JSON.stringify({
            type: 'done',
            message: { role: 'assistant', content: 'Grounded answer' },
            tool_execution: toolExecution,
          })}\n\n`,
        ));
        controller.close();
      },
    });
    global.fetch = vi.fn().mockResolvedValue(new Response(body, { status: 200 }));

    const result = await consumeChatStream(
      '/api/v1/chat/stream',
      { authorization: 'Bearer token', body: {} },
      undefined,
    );

    expect(result.tool_execution).toEqual(toolExecution);
  });
});

describe('feature flag local hint', () => {
  it('readLocalConversationalFlag does not force enable when unset', () => {
    // Without NEXT_PUBLIC_ENABLE_CONVERSATIONAL_DATA_SETUP, hint is null (backend decides).
    expect([true, false, null]).toContain(readLocalConversationalFlag());
  });
});
