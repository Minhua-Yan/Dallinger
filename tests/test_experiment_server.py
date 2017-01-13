import json
import os
import unittest

import pytest


class FlaskAppTest(unittest.TestCase):
    """Base test case class for tests of the flask app."""

    def setUp(self, case=None):
        # The flask app assumes it is imported
        # while in an experiment directory.
        # `tests/experiment` mimics the files that are put
        # in place by dallinger.command_line.setup_experiment
        # when running via the CLI
        os.chdir('tests/experiment')

        from dallinger.experiment_server.experiment_server import app
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
        self.app = app.test_client()

        import dallinger.db
        self.db = dallinger.db.init_db(drop_all=True)

        # For now, clear and init the psiturk db too
        import psiturk.db
        psiturk.db.Base.metadata.drop_all(bind=psiturk.db.engine)
        psiturk.db.init_db()

    def tearDown(self):
        self.db.rollback()
        self.db.close()
        os.chdir('../..')


class TestExperimentServer(FlaskAppTest):
    worker_counter = 0
    hit_counter = 0
    assignment_counter = 0

    def _create_participant(self):
        worker_id = self.worker_counter
        hit_id = self.hit_counter
        assignment_id = self.assignment_counter
        self.worker_counter += 1
        self.hit_counter += 1
        self.assignment_counter += 1
        resp = self.app.post('/participant/{}/{}/{}/debug'.format(
            worker_id, hit_id, assignment_id
        ))
        return json.loads(resp.data).get('participant', {}).get('id')

    def _create_node(self, participant_id):
        resp = self.app.post('/node/{}'.format(participant_id))
        return json.loads(resp.data).get('node', {}).get('id')

    def _update_participant_status(self, participant_id, status):
        from dallinger.models import Participant
        participant = Participant.query.get(participant_id)
        participant.status = status

    def test_default(self):
        resp = self.app.get('/')
        assert 'Welcome to Dallinger!' in resp.data

    def test_favicon(self):
        resp = self.app.get('/favicon.ico')
        assert resp.content_type == 'image/x-icon'
        assert resp.content_length > 0

    def test_robots(self):
        resp = self.app.get('/robots.txt')
        assert 'User-agent' in resp.data

    def test_ad(self):
        resp = self.app.get('/ad', query_string={
            'hitId': 'debug',
            'assignmentId': '1',
            'mode': 'debug',
        })
        assert 'Psychology Experiment' in resp.data

    def test_ad_no_params(self):
        resp = self.app.get('/ad')
        assert resp.status_code == 500
        assert 'Psychology Experiment - Error' in resp.data

    def test_consent(self):
        resp = self.app.get('/consent', query_string={
            'hit_id': 'debug',
            'assignment_id': '1',
            'worker_id': '1',
            'mode': 'debug',
        })
        assert 'Informed Consent Form' in resp.data

    @pytest.mark.xfail(reason="#411")
    def test_participant_info(self):
        p_id = self._create_participant()
        resp = self.app.get('/participant/{}'.format(p_id))
        data = json.loads(resp.data)
        assert data.get('status') == 'success'
        assert data.get('participant').get('status') == u'working'

    @pytest.mark.xfail(reason="#411")
    def test_node_vectors(self):
        p_id = self._create_participant()
        n_id = self._create_node(p_id)
        resp = self.app.get('/node/{}/vectors'.format(n_id))
        data = json.loads(resp.data)
        assert data.get('status') == 'success'
        assert data.get('vectors') == []

    @pytest.mark.xfail(reason="#411")
    def test_node_infos(self):
        p_id = self._create_participant()
        n_id = self._create_node(p_id)
        resp = self.app.get('/node/{}/infos'.format(n_id))
        data = json.loads(resp.data)
        assert data.get('status') == 'success'
        assert data.get('infos') == []

    @pytest.mark.xfail(reason="#411")
    def test_summary(self):
        resp = self.app.get('/summary')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get('status') == 'success'
        assert data.get('completed') is False
        assert data.get('unfilled_networks') == 1
        assert data.get('required_nodes') == 2
        assert data.get('nodes_remaining') == 2
        assert data.get('summary') == []

        p1_id = self._create_participant()
        self._create_node(p1_id)
        resp = self.app.get('/summary')
        data = json.loads(resp.data)
        assert data.get('completed') is False
        assert data.get('nodes_remaining') == 1
        worker_summary = data.get('summary')
        assert len(worker_summary) == 1
        assert worker_summary[0] == [u'working', 1]

        p2_id = self._create_participant()
        self._create_node(p2_id)
        resp = self.app.get('/summary')
        data = json.loads(resp.data)
        assert data.get('completed') is False
        assert data.get('nodes_remaining') == 0
        worker_summary = data.get('summary')
        assert len(worker_summary) == 1
        assert worker_summary[0] == [u'working', 2]

        self._update_participant_status(p1_id, 'submitted')
        self._update_participant_status(p2_id, 'approved')

        resp = self.app.get('/summary')
        data = json.loads(resp.data)
        assert data.get('completed') is True
        worker_summary = data.get('summary')
        assert len(worker_summary) == 2
        assert worker_summary[0] == [u'approved', 1]
        assert worker_summary[1] == [u'submitted', 1]

    def test_not_found(self):
        resp = self.app.get('/BOGUS')
        assert resp.status_code == 404