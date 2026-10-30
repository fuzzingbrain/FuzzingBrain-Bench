import json
from pathlib import Path

import pytest
from fbbench.report import summary
from fbbench.sweep.orchestrator import cell_dir


def episode(root, challenge, signatures, sample=0, model='test-model'):
    p = cell_dir(root, challenge, model, sample)
    p.mkdir(parents=True, exist_ok=True)
    (p / 'score.json').write_text(json.dumps({'crash_signatures': signatures,
                                            'unique_crashes': len(set(signatures))}))


def test_published_matrix_and_maximum():
    matrix, cap, maximum = summary._load_difficulty()
    assert len(matrix) == 77 and cap == 3 and maximum == 736
    assert [[sum(w[j] == level for w in matrix.values()) for level in range(1, 6)]
            for j in range(3)] == [[33, 15, 16, 6, 7], [11, 12, 16, 14, 24], [4, 6, 13, 18, 36]]


@pytest.mark.parametrize('count,points', [(0, 0), (1, 4), (2, 8), (3, 13), (8, 13)])
def test_position_weights_and_cap(tmp_path, count, points):
    episode(tmp_path, 'arrow-01', [f's{i}' for i in range(count)])
    result = summary.build_summary(tmp_path)
    assert result['scores']['test-model']['scored'] == points
    assert result['scores']['test-model']['max'] == 13
    assert result['pairs']['arrow-01 test-model']['weighted_score'] == points
    assert result['cells'][0]['difficulty_weights'] == [4, 4, 5]


def test_sample_union_does_not_double_count(tmp_path):
    episode(tmp_path, 'arrow-01', ['one'])
    episode(tmp_path, 'arrow-01', ['one', 'two'], sample=1)
    result = summary.build_summary(tmp_path)
    assert result['scores']['test-model']['scored'] == 8
    assert result['pairs']['arrow-01 test-model']['crashes'] == 2


def test_full_corpus_maximum_and_unknown_challenge(tmp_path):
    matrix, _, _ = summary._load_difficulty()
    for c in matrix:
        episode(tmp_path, c, ['a', 'b', 'c', 'd'])
    episode(tmp_path, 'unlisted', ['a'])
    result = summary.build_summary(tmp_path)
    assert result['scores']['test-model'] == dict(scored=736, max=736, challenges_run=78, unscored=['unlisted'])
    assert result['pairs']['unlisted test-model']['weighted_score'] is None


def test_equal_size_different_challenge_sets_are_not_comparable(tmp_path):
    episode(tmp_path, 'arrow-01', ['a'], model='a')
    episode(tmp_path, 'assimp-01', ['a'], model='b')
    assert not summary.build_summary(tmp_path)['comparable']


def test_scalar_or_corrupt_metadata_is_rejected(tmp_path, monkeypatch):
    p = tmp_path / 'difficulty.json'
    monkeypatch.setattr(summary, '_DIFFICULTY', p)
    for matrix, maximum in [({'a': 3}, 9), ({'a': [4, 3, 5]}, 12), ({'a': [1, 2, 3]}, 7)]:
        p.write_text(json.dumps({'difficulty': matrix, 'cap': 3, 'max_score': maximum}))
        with pytest.raises(ValueError):
            summary._load_difficulty()


def test_html_renders_matrix_score(tmp_path):
    import re
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is needed for the report rendering check')
    episode(tmp_path, 'arrow-01', ['a', 'b', 'c'])
    html = summary.write_summary(tmp_path).read_text()
    html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    data = re.search(r'<script[^>]*id="data"[^>]*>(.*?)</script>', html, re.S).group(1)
    script = re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', html, re.S)[-1]
    js = ('const nodes={}; const document={getElementById(id){return nodes[id] ||= '
          '{innerHTML:"", textContent:"", addEventListener(){}};}};\n'
          'nodes.data={textContent:' + json.dumps(data) + '};\n' + script +
          '\nif(!nodes.matrix.innerHTML.includes("4 / 4 / 5") || '
          '!nodes.matrix.innerHTML.includes(">13</td>")) throw Error("Matrix rendering mismatch");')
    path = tmp_path / 'render.js'; path.write_text(js)
    subprocess.run([node, str(path)], check=True, capture_output=True, text=True)
