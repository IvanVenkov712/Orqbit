import json
from io import BytesIO
from queue import Queue
from threading import Event, Thread
from unittest.mock import Mock, call
from urllib.error import HTTPError, URLError
from uuid import UUID

import pytest
from pydantic import ValidationError

import api
import producer
from settings import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ("API_KEY", "API_URL", "POLL_INTERVAL", "REQUEST_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(monkeypatch):
    settings = Settings(
        _env_file=None, api_key="producer-key", api_url="http://localhost:8000"
    )
    monkeypatch.setattr(producer, "Settings", lambda: settings)
    return settings


@pytest.fixture
def state():
    return Queue(), {}, {}, Event()


def test_http_submission_and_status_use_producer_auth(monkeypatch, settings):
    def respond(request, timeout):
        assert request.get_header("X-api-key") == "producer-key"
        assert timeout == settings.request_timeout
        if request.get_method() == "POST":
            assert request.full_url == "http://localhost:8000/producer/jobs"
            assert request.get_header("Idempotency-key") == "original-key"
            assert request.get_header("Content-type") == "application/json"
            assert json.loads(request.data) == {
                "job_type": "add_numbers",
                "params": {"numbers": [2, 3, 4, 8]},
                "permission_policy": "PRIVATE",
            }
        else:
            assert request.get_method() == "GET"
            assert request.full_url == "http://localhost:8000/producer/jobs/42"
            assert request.data is None
        return BytesIO(b'{"id": 42, "status": "PENDING"}')

    monkeypatch.setattr(api, "urlopen", respond)
    assert api.submit_job(settings, [2, 3, 4, 8], "original-key")["id"] == 42
    assert api.get_job(settings, 42)["status"] == "PENDING"


@pytest.mark.parametrize(
    "line", ["", " ", "true", '"2"', "NaN", "Infinity", "1e999", "2 bad", "[]", "{}"]
)
def test_invalid_numbers_are_rejected(line):
    with pytest.raises(ValueError, match="finite numbers"):
        producer.parse_numbers(line)


def test_numbers_accept_negative_decimals_exponents_and_whitespace():
    assert producer.parse_numbers(" 2\t-3.5  4e2\n") == [2, -3.5, 400.0]


def test_each_valid_line_gets_a_new_automatic_key(monkeypatch, settings, capsys):
    thread = Mock(ident=None)
    constructor = Mock(return_value=thread)
    monkeypatch.setattr(producer, "Thread", constructor)
    monkeypatch.setattr(
        "builtins.input",
        Mock(side_effect=["bad", " ", "2 3", "2 3", KeyboardInterrupt]),
    )

    assert producer.main() == 130
    submissions = constructor.call_args.kwargs["args"][1]
    stop = constructor.call_args.kwargs["args"][2]
    first, second = submissions.get_nowait(), submissions.get_nowait()
    assert first[1] == second[1] == [2, 3]
    assert first[0] != second[0]
    assert UUID(first[0]).version == UUID(second[0]).version == 4
    assert submissions.empty()
    assert stop.is_set()
    assert constructor.call_args.kwargs["daemon"] is True
    assert "finite numbers" in capsys.readouterr().err


def test_completed_jobs_print_once_and_do_not_block_other_jobs(
    monkeypatch, settings, state, capsys
):
    submissions, pending, jobs, stop = state
    jobs.update({42: [2, 3, 4, 8], 43: [6, 7, 9, 3]})
    get = Mock(
        side_effect=[
            {"status": "RUNNING"},
            {"status": "SUCCEEDED", "result": {"sum": 25}},
            {"status": "SUCCEEDED", "result": {"sum": 17}},
        ]
    )
    monkeypatch.setattr(producer, "get_job", get)

    producer.process_once(settings, *state)
    assert jobs == {42: [2, 3, 4, 8]}
    producer.process_once(settings, *state)
    producer.process_once(settings, *state)
    assert not jobs
    assert get.call_args_list == [
        call(settings, 42),
        call(settings, 43),
        call(settings, 42),
    ]
    assert capsys.readouterr().out.splitlines() == [
        "6 + 7 + 9 + 3 = 25",
        "2 + 3 + 4 + 8 = 17",
    ]


def test_failed_job_is_reported_once_and_forgotten(
    monkeypatch, settings, state, capsys
):
    state[2][42] = [2, 3]
    get = Mock(return_value={"status": "FAILED", "error": {"code": "INVALID_PARAMS"}})
    monkeypatch.setattr(producer, "get_job", get)
    producer.process_once(settings, *state)
    producer.process_once(settings, *state)
    get.assert_called_once_with(settings, 42)
    assert not state[2]
    assert 'Job 42 failed: {"code": "INVALID_PARAMS"}' in capsys.readouterr().out


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("private"),
        URLError("private"),
        HTTPError("private", 503, "private", {}, None),
        HTTPError("private", 429, "private", {}, None),
    ],
)
def test_uncertain_submission_retries_identical_key_and_content(
    monkeypatch, settings, state, error, capsys
):
    state[0].put(("original-key", [2, 3, 4, 8]))
    submit = Mock(side_effect=[error, {"id": 42}])
    monkeypatch.setattr(producer, "submit_job", submit)
    monkeypatch.setattr(producer, "get_job", Mock(return_value={"status": "PENDING"}))
    producer.process_once(settings, *state)
    assert state[1] == {"original-key": [2, 3, 4, 8]}
    assert not state[2]
    producer.process_once(settings, *state)
    assert submit.call_args_list == [call(settings, [2, 3, 4, 8], "original-key")] * 2
    assert not state[1]
    assert state[2] == {42: [2, 3, 4, 8]}
    assert "private" not in capsys.readouterr().err


@pytest.mark.parametrize("status", [401, 409, 422])
def test_rejected_submission_is_not_retried(
    monkeypatch, settings, state, status, capsys
):
    state[0].put(("key", [2]))
    submit = Mock(side_effect=HTTPError("private", status, "private", {}, None))
    monkeypatch.setattr(producer, "submit_job", submit)
    producer.process_once(settings, *state)
    producer.process_once(settings, *state)
    submit.assert_called_once()
    assert not state[1] and not state[2]
    error = capsys.readouterr().err
    assert f"HTTP {status}" in error
    assert "private" not in error


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("private"),
        HTTPError("private", 503, "private", {}, None),
        KeyError("private"),
    ],
)
def test_poll_errors_keep_job_for_later_completion(
    monkeypatch, settings, state, error, capsys
):
    state[2][42] = [2, 3]
    get = Mock(side_effect=[error, {"status": "SUCCEEDED", "result": {"sum": 5}}])
    monkeypatch.setattr(producer, "get_job", get)
    producer.process_once(settings, *state)
    assert 42 in state[2]
    producer.process_once(settings, *state)
    assert not state[2]
    output = capsys.readouterr()
    assert "2 + 3 = 5" in output.out
    assert "private" not in output.err


def test_shutdown_does_not_start_more_requests(monkeypatch, settings, state):
    state[0].put(("key", [2]))
    state[2][42] = [3]
    state[3].set()
    submit, get = Mock(), Mock()
    monkeypatch.setattr(producer, "submit_job", submit)
    monkeypatch.setattr(producer, "get_job", get)
    producer.process_once(settings, *state)
    submit.assert_not_called()
    get.assert_not_called()


def test_background_loop_uses_configured_interruptible_interval(monkeypatch, settings):
    stop = Event()
    wait = Mock(side_effect=lambda seconds: stop.set())
    monkeypatch.setattr(stop, "wait", wait)
    monkeypatch.setattr(producer, "process_once", Mock())
    producer.run(settings, Queue(), stop)
    wait.assert_called_once_with(settings.poll_interval)
    assert settings.poll_interval == 2


def test_input_and_completion_continue_while_other_work_is_pending(
    monkeypatch, settings, capsys
):
    settings = settings.model_copy(update={"poll_interval": 0.01})
    monkeypatch.setattr(producer, "Settings", lambda: settings)
    first_request = Event()
    second_line_queued = Event()
    both_finished = Event()
    threads = []

    def make_thread(**kwargs):
        thread = Thread(**kwargs)
        threads.append(thread)
        return thread

    def submit(config, numbers, key):
        if numbers == [2, 3, 4, 8]:
            first_request.set()
            assert second_line_queued.wait(3), "input stopped while HTTP was blocked"
            return {"id": 42}
        assert numbers == [6, 7, 9, 3]
        return {"id": 43}

    original_process = producer.process_once

    def process(config, submissions, pending, jobs, stop):
        original_process(config, submissions, pending, jobs, stop)
        if submit_mock.call_count == 2 and not pending and not jobs:
            both_finished.set()

    inputs = iter(["2 3 4 8", "6 7 9 3"])

    def read_line():
        line = next(inputs, None)
        if line == "6 7 9 3":
            assert first_request.wait(3), "background did not submit the first line"
        if line is None:
            second_line_queued.set()
            assert both_finished.wait(3), "results were blocked by console input"
            raise KeyboardInterrupt
        return line

    submit_mock = Mock(side_effect=submit)
    monkeypatch.setattr(producer, "Thread", make_thread)
    monkeypatch.setattr(producer, "submit_job", submit_mock)
    monkeypatch.setattr(producer, "process_once", process)
    monkeypatch.setattr(
        producer,
        "get_job",
        lambda config, job_id: {
            "status": "SUCCEEDED",
            "result": {"sum": 17 if job_id == 42 else 25},
        },
    )
    monkeypatch.setattr("builtins.input", read_line)

    assert producer.main() == 130
    assert both_finished.is_set()
    assert all(not thread.is_alive() for thread in threads)
    output = capsys.readouterr().out
    assert output.count("2 + 3 + 4 + 8 = 17") == 1
    assert output.count("6 + 7 + 9 + 3 = 25") == 1


def test_eof_stops_and_wakes_background_thread(monkeypatch, settings):
    stop = Event()
    stopped = Event()
    started = Event()

    def background(config, submissions, signal):
        started.set()
        signal.wait()
        stop.set()
        stopped.set()

    def read_line():
        assert started.wait(3)
        raise EOFError

    monkeypatch.setattr(producer, "run", background)
    monkeypatch.setattr("builtins.input", read_line)
    assert producer.main() == 0
    assert stop.is_set() and stopped.is_set()


@pytest.mark.parametrize("field", ["poll_interval", "request_timeout"])
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_timing_configuration(field, value):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            api_key="key",
            api_url="http://localhost:8000",
            **{field: value},
        )


def test_bad_configuration_does_not_start_background_thread(monkeypatch, capsys):
    def configure():
        return Settings(_env_file=None, api_key="private-key")

    constructor = Mock()
    monkeypatch.setattr(producer, "Settings", configure)
    monkeypatch.setattr(producer, "Thread", constructor)
    assert producer.main() == 1
    constructor.assert_not_called()
    error = capsys.readouterr().err
    assert "Invalid producer configuration" in error
    assert "private-key" not in error
