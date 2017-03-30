import events
from sim_interface import TraceReader
import json
import pickle
import gzip


class JsonTraceReader(TraceReader):
    def __init__(self, filename):
        self.trace_filename = filename
        self.trace_logs = None
        self.trace_pos = 0
        self.start_time = None
        self.end_time = None

    def build(self):
        if self.trace_filename.endswith('.json'):
            with open(self.trace_filename, 'r') as fp:
                self.trace_logs = json.load(fp, object_hook=events.json_decode_event)
        elif self.trace_filename.endswith('.json.gz'):
            with gzip.open(self.trace_filename, 'rt') as fp:
                self.trace_logs = json.load(fp, object_hook=events.json_decode_event)
        else:
            raise Exception('Invalid JSON file type. Expected .json or .json.gz')

        # Identify start and end time of trace
        self.start_time = self.trace_logs[0].timestamp
        self.end_time = self.trace_logs[-1].timestamp

    def finish(self):
        pass

    def get_event(self):
        if self.end_of_trace():
            return None

        event = self.trace_logs[self.trace_pos]
        self.trace_pos += 1
        return event

    def peek_event(self):
        if self.end_of_trace():
            return None

        event = self.trace_logs[self.trace_pos]
        return event

    def end_of_trace(self):
        return self.trace_pos >= len(self.trace_logs)

    def get_events(self, count):
        events_list = []
        for i in range(count):
            event = self.get_event()
            if event:
                events_list.append(event)
            else:
                break
        return events_list

    def get_start_time(self):
        return self.start_time

    def get_end_time(self):
        return self.end_time


class PickleTraceReader(TraceReader):
    def __init__(self, filename):
        self.trace_filename = filename
        self.trace_logs = None
        self.trace_pos = 0
        self.start_time = None
        self.end_time = None

    def build(self):
        if self.trace_filename.endswith('.pkl'):
            with open(self.trace_filename, 'r') as fp:
                self.trace_logs = pickle.load(fp)
        elif self.trace_filename.endswith('.pkl.gz'):
            with gzip.open(self.trace_filename, 'rb') as fp:
                self.trace_logs = pickle.load(fp)
        else:
            raise Exception('Invalid JSON file type. Expected .json or .json.gz')

        # Identify start and end time of trace
        self.start_time = self.trace_logs[0].timestamp
        self.end_time = self.trace_logs[-1].timestamp

    def finish(self):
        pass

    def get_event(self):
        if self.end_of_trace():
            return None

        event = self.trace_logs[self.trace_pos]
        self.trace_pos += 1
        return event

    def peek_event(self):
        if self.end_of_trace():
            return None

        event = self.trace_logs[self.trace_pos]
        return event

    def end_of_trace(self):
        return self.trace_pos >= len(self.trace_logs)

    def get_events(self, count):
        events_list = []
        for i in range(count):
            event = self.get_event()
            if event:
                events_list.append(event)
            else:
                break
        return events_list

    def get_start_time(self):
        return self.start_time

    def get_end_time(self):
        return self.end_time


def get_trace_reader(filename, trace_type=None):
    if trace_type:
        if trace_type == 'json':
            return JsonTraceReader(filename=filename)
        elif trace_type == 'pickle':
            return PickleTraceReader(filename=filename)
        else:
            raise Exception("Invalid Trace File Type")
    else:
        if filename.endswith('.json') or filename.endswith('.json.gz'):
            return JsonTraceReader(filename=filename)
        elif filename.endswith('.pkl') or filename.endswith('.pkl.gz'):
            return PickleTraceReader(filename=filename)
        else:
            raise Exception("Invalid Trace File Type")
