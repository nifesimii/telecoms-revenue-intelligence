import test from 'node:test';
import assert from 'node:assert/strict';
import { assistantPresentation, commissionTerminology, RATE_CARD_CAUSE } from '../src/lib/commissionTerminology.js';
import { evidenceReport, detailText } from '../src/components/audit/auditPresentation.js';

test('assistant presentation updates legacy causes without mutating stored content or user words', () => {
  const original = { role: 'assistant', content: 'USP snapshot miss. Check the calculation-month USP snapshot.', raw_data: { source: 'usp_dimension' } };
  const saved = JSON.stringify(original);
  const presented = assistantPresentation(original);
  assert.equal(presented.content, `${RATE_CARD_CAUSE}. Check the calculation-month commission rate card snapshot.`);
  assert.equal(JSON.stringify(original), saved);
  assert.equal(commissionTerminology("It's a USP snapshot miss in the USP snapshot; the dealer's amount is unchanged."), "It's a Product not matched to commission rate card in the commission rate card snapshot; the dealer's amount is unchanged.");
  const user = { role: 'user', content: original.content };
  assert.strictEqual(assistantPresentation(user), user);
});

test('quotes, source identifiers, code, links and numeric selling price retain their meaning', () => {
  const protectedText = [
    '"USP snapshot miss"', "'USP snapshot miss'", '“USP snapshot miss”',
    '> USP snapshot miss', '    USP snapshot miss', '`USP snapshot miss`',
    '```text\nUSP snapshot miss\n```', '~~~\nUSP snapshot miss\n~~~',
    'development.usp_dimension USP_SNAPSHOT_MISS usp_snapshot_period unit_selling_price',
    '[source](https://example.com/USP)', 'Unit Selling Price: NGN 10,000.00',
    'The marketing USP is unrelated.',
    '> Quoted evidence\nUSP snapshot miss',
  ].join('\n\n');
  assert.equal(commissionTerminology(protectedText), protectedText);
  assert.equal(commissionTerminology('```text\nUSP snapshot miss'), '```text\nUSP snapshot miss');
  assert.equal(commissionTerminology(`${protectedText}\n\nUSP snapshot miss`), `${protectedText}\n\n${RATE_CARD_CAUSE}`);
});

test('saved audit displays and exports translate prose and compatibility keys without rewriting evidence', () => {
  const trail = { partner_name: 'Example', partner_code: '001', module: 'eligibility_window',
    limitations: ['Review USP coverage'], steps: [{ step: 1, name: 'usp_lookup',
      checked: 'Review the USP snapshot', result: 'USP snapshot miss',
      caveat: 'Product missing from USP.', presentation_qualification: 'Review USP coverage',
      detail: { usp_snapshot_miss: 2, products_missing_from_usp: ['P1'], source: 'usp_dimension', unit_selling_price: 10000, user_note: 'USP snapshot miss', product_code: 'usp_snapshot_miss', alt_root_causes: ['usp_snapshot_miss'] } }] };
  const original = JSON.stringify(trail);
  const report = evidenceReport(trail);
  assert.match(report, /Product not matched to commission rate card: 2/);
  assert.match(report, /Products not matched to commission rate card/);
  assert.match(report, /calculation|commission rate card snapshot/);
  assert.match(report, /usp_dimension/);
  assert.match(report, /User note: USP snapshot miss/);
  assert.match(report, /Product code: usp_snapshot_miss/);
  assert.match(report, /Alt root causes:.*Product not matched/s);
  assert.doesNotMatch(report, /Usp snapshot|USP coverage|missing from USP/);
  assert.equal(JSON.stringify(trail), original);
  assert.equal(detailText({ usp_missing: 4 }), 'Missing partner classification: 4');
});

test('multiline quotations and code spans with shorter backtick runs remain verbatim', () => {
  const quoted = 'The dealer said "First line\nUSP snapshot miss".';
  const singleQuoted = "The dealer said 'First line\nUSP snapshot miss'.";
  const code = 'Code: ``first ` USP snapshot miss``';
  for (const protectedText of [quoted, singleQuoted, code, 'Code: ```first `` USP snapshot miss```']) {
    const input = `${protectedText}\n\nUSP snapshot miss`;
    assert.equal(commissionTerminology(input), `${protectedText}\n\n${RATE_CARD_CAUSE}`);
  }
});

test('historical classification and source-reference prose use their distinct canonical terms', () => {
  const message = { role: 'assistant', content: '## USP missing — NULL account_profile_class\nCheck against the USP; product absent from the USP.' };
  assert.equal(assistantPresentation(message).content, '## Missing partner classification — NULL account_profile_class\nCheck against the commission rate card; product absent from the commission rate card.');
  assert.equal(commissionTerminology('"USP missing" `against the USP`'), '"USP missing" `against the USP`');
});

test('fenced code closes only with the opening character and at least its length', () => {
  const blocks = [
    '````markdown\n```\nUSP snapshot miss\n```\n````',
    '~~~~markdown\n~~~\nUSP snapshot miss\n~~~\n~~~~',
    '```text\n~~~\nUSP snapshot miss\n```',
    '~~~text\n```\nUSP snapshot miss\n~~~',
    '````text\nUSP snapshot miss\n`````',
  ];
  for (const block of blocks) {
    assert.equal(commissionTerminology(`${block}\n\nUSP snapshot miss`), `${block}\n\n${RATE_CARD_CAUSE}`);
  }
  const unclosed = '````text\n```\nUSP snapshot miss\n```';
  assert.equal(commissionTerminology(unclosed), unclosed);
});
