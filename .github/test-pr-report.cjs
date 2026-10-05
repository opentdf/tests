const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const workflow = fs.readFileSync(path.join(__dirname, 'workflows/xtest.yml'), 'utf8');
const exportJob = workflow.split('  export-pr-report:')[1].split('  publish-results:')[0];
const script = exportJob.split('          script: |\n')[1].split('      - uses:')[0]
  .split('\n').map(line => line.replace(/^            /, '')).join('\n');

async function execute(result = 'success', jobs = [{ name: 'platform-xtest / xct (main, go)', status: 'completed' }]) {
  let output;
  const artifacts = [
    { id: 1, name: 'old', created_at: '2026-09-01', expired: false },
    { id: 2, name: 'current', created_at: '2026-10-05T10:00:00Z', expired: false },
    { id: 3, name: 'expired', created_at: '2026-10-05T10:00:00Z', expired: true }
  ];
  const listArtifacts = Symbol('artifacts');
  const listJobs = Symbol('jobs');
  const sandbox = {
    require: name => { assert.equal(name, 'fs'); return { mkdirSync() {}, writeFileSync(p, text) { output = JSON.parse(text); } }; },
    process: { env: { RUNNER_TEMP: '/tmp/fake', GITHUB_RUN_ATTEMPT: '2', XCT_RESULT: result } },
    context: { repo: { owner: 'opentdf', repo: 'platform' }, runId: 7, sha: 'merge', payload: { pull_request: { number: 12, head: { sha: 'head' } } } },
    github: { paginate: async method => method === listArtifacts ? artifacts : jobs, rest: { actions: {
      listWorkflowRunArtifacts: listArtifacts, listJobsForWorkflowRunAttempt: listJobs,
      getWorkflowRunAttempt: async () => ({ data: { run_started_at: '2026-10-05T09:00:00Z' } })
    } } }
  };
  await vm.runInNewContext(`(async () => { ${script} })()`, sandbox);
  return output;
}

test('opt-in only workflow_call preserves all existing callers and publisher permissions', () => {
  const called = workflow.split('  workflow_call:')[1].split('  schedule:')[0];
  assert.match(called, /consolidated-pr-report:[\s\S]*?type: boolean\n        default: false/);
  assert.match(workflow, /if: always\(\) && !inputs.consolidated-pr-report/);
  assert.match(exportJob, /if: always\(\) && inputs.consolidated-pr-report/);
  assert.match(exportJob, /permissions:\n      actions: read/);
  assert.ok(!exportJob.includes('pull-requests: write'));
  assert.ok(!exportJob.includes('createComment'));
  assert.match(exportJob, /name: pr-report-xtest-\$\{\{ github.run_id \}\}-\$\{\{ github.run_attempt \}\}/);
});

test('structured caller identity and current attempt artifacts, not log scraping', async () => {
  const section = await execute();
  assert.deepEqual(Object.keys(section).sort(), ['version', 'section', 'title', 'status', 'summary', 'details', 'repository', 'pr', 'sha', 'run', 'attempt'].sort());
  assert.equal(section.status, 'passed');
  assert.equal(section.repository, 'opentdf/platform');
  assert.equal(section.sha, 'head');
  assert.equal(section.pr, 12);
  assert.equal(section.run, 7);
  assert.equal(section.attempt, 2);
  assert.match(section.details, /current/);
  assert.ok(!section.details.includes('old'));
  assert.ok(!section.details.includes('expired'));
});

test('failed/cancelled/skipped and partial reruns remain meaningful', async () => {
  for (const [result, expected] of [['failure', 'failed'], ['cancelled', 'cancelled'], ['skipped', 'unavailable']]) {
    assert.equal((await execute(result)).status, expected);
  }
  assert.equal((await execute('success', [])).status, 'unavailable');
  assert.equal((await execute('success', [{ name: 'xct (main, go)', status: 'in_progress' }])).status, 'unavailable');
});
