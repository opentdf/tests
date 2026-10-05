const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const workflow = fs.readFileSync(path.join(__dirname, 'workflows/xtest.yml'), 'utf8');
const exportJob = workflow.split('  export-pr-report:')[1].split('  publish-results:')[0];
const script = exportJob.split('          script: |\n')[1].split('      - uses:')[0]
  .split('\n').map(line => line.replace(/^            /, '')).join('\n');

const platforms = ['pull-123', 'v0.12.0', 'main']; // Resolved head, lts and main, not raw ref aliases.
const sdks = ['go@pull-123', 'go@main', 'js@main'];
const allCells = () => platforms.flatMap(platform => sdks.map(sdk => ({
  name: `platform-xtest / xct (${platform}, ${sdk})`, status: 'completed', conclusion: 'success'
})));

async function execute(jobs = allCells(), env = {}) {
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
    process: { env: { RUNNER_TEMP: '/tmp/fake', GITHUB_RUN_ATTEMPT: '2',
      RESOLVE_RESULT: 'success', PLATFORM_TAGS: JSON.stringify(platforms), SDK_VERSIONS: JSON.stringify(sdks), ...env } },
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

test('complete current-attempt conclusions determine failure/cancellation/skipped without retained aggregate', async () => {
  for (const [conclusion, expected] of [['failure', 'failed'], ['timed_out', 'failed'], ['cancelled', 'cancelled'], ['skipped', 'unavailable']]) {
    const jobs = allCells();
    jobs[0].conclusion = conclusion;
    assert.equal((await execute(jobs, { XCT_RESULT: 'success' })).status, expected);
  }
  // A retained failed aggregate cannot override a complete successful current attempt either.
  assert.equal((await execute(allCells(), { XCT_RESULT: 'failure' })).status, 'passed');
});

test('nonempty strict subsets cannot pass against the actual multi-axis resolved matrix', async () => {
  for (const jobs of [[], allCells().slice(0, 1), allCells().slice(0, -1), allCells().slice(0, 3)]) {
    const section = await execute(jobs, { XCT_RESULT: 'success' });
    assert.equal(section.status, 'unavailable');
    assert.match(section.summary, /prior-attempt results are not reused/);
  }
  const unfinished = allCells();
  unfinished[0].status = 'in_progress';
  assert.equal((await execute(unfinished)).status, 'unavailable');
});

test('expected identities reject duplicate/unexpected cells and invalid resolution, accept direct callers', async () => {
  assert.equal((await execute([...allCells(), allCells()[0]])).status, 'unavailable');
  const wrong = allCells();
  wrong[0].name = 'platform-xtest / xct (lts, go@main)'; // Raw alias is not resolved identity.
  assert.equal((await execute(wrong)).status, 'unavailable');
  for (const env of [{ PLATFORM_TAGS: '[]' }, { SDK_VERSIONS: 'broken' },
    { PLATFORM_TAGS: '["main","main"]' }, { SDK_VERSIONS: '[null]' }, { RESOLVE_RESULT: 'failure' }]) {
    assert.equal((await execute(allCells(), env)).status, 'unavailable');
  }
  const direct = allCells().map(job => ({ ...job, name: job.name.replace('platform-xtest / ', '') }));
  assert.equal((await execute(direct)).status, 'passed');
});

test('export derives exactly the xct resolved Cartesian product without changing capstone checks', () => {
  const xct = workflow.split('  xct:')[1].split('  bench:')[0];
  assert.match(xct, /platform-tag: \$\{\{ fromJSON\(needs.resolve-versions.outputs.platform-tag-list\) \}\}/);
  assert.match(xct, /sdk-version: \$\{\{ fromJSON\(needs.resolve-versions.outputs.sdk-version-list\) \}\}/);
  assert.match(exportJob, /needs: \[resolve-versions, xct\]/);
  assert.match(exportJob, /PLATFORM_TAGS: \$\{\{ needs.resolve-versions.outputs.platform-tag-list \}\}/);
  assert.match(exportJob, /SDK_VERSIONS: \$\{\{ needs.resolve-versions.outputs.sdk-version-list \}\}/);
  const capstone = workflow.split('\n  xtest:')[1];
  assert.match(capstone, /needs: xct/);
  assert.match(capstone, /needs.xct.result == 'failure'/);
});
