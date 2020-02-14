# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
Predefined step definitions for handling dialog interaction with Mycroft for
use with behave.
"""
from os.path import join, exists, basename
from glob import glob
import re
import time

from behave import given, when, then

from mycroft.messagebus import Message
from mycroft.audio import wait_while_speaking


TIMEOUT = 10


def find_dialog(skill_path, dialog):
    """Check the usual location for dialogs.

    TODO: subfolders
    """
    if exists(join(skill_path, 'dialog')):
        return join(skill_path, 'dialog', 'en-us', dialog)
    else:
        return join(skill_path, 'locale', 'en-us', dialog)


def load_dialog_file(dialog_path):
    """Load dialog files and get the contents."""
    with open(dialog_path) as f:
        lines = f.readlines()
    return [l.strip().lower() for l in lines
            if l.strip() != '' and l.strip()[0] != '#']


def load_dialog_list(skill_path, dialog):
    """Load dialog from files into a single list.

    Arguments:
        skill (MycroftSkill): skill to load dialog from
        dialog (list): Dialog names (str) to load

    Returns:
        tuple (list of Expanded dialog strings, debug string)
    """
    dialog_path = find_dialog(skill_path, dialog)

    debug = 'Opening {}\n'.format(dialog_path)
    return load_dialog_file(dialog_path), debug


def dialog_from_sentence(sentence, skill_path):
    """Find dialog file from example sentence."""
    dialog_paths = join(skill_path, 'dialog', 'en-us', '*.dialog')
    best = (None, 0)
    for path in glob(dialog_paths):
        patterns = load_dialog_file(path)
        match, _ = _match_dialog_patterns(patterns, sentence.lower())
        if match is not False:
            if len(patterns[match]) > best[1]:
                best = (path, len(patterns[match]))
    if best[0] is not None:
        return basename(best[0])
    else:
        return None


def _match_dialog_patterns(dialogs, sentence):
    """Match sentence against a list of dialog patterns.

    Returns index of found match.
    """
    # Allow custom fields to be anything
    dialogs = [re.sub(r'{.*?\}', r'.*', dia) for dia in dialogs]
    # Remove left over '}'
    dialogs = [re.sub(r'\}', r'', dia) for dia in dialogs]
    dialogs = [re.sub(r' .* ', r' .*', dia) for dia in dialogs]
    # Merge consequtive .*'s into a single .*
    dialogs = [re.sub(r'\.\*( \.\*)+', r'.*', dia) for dia in dialogs]
    # Remove double whitespaces
    dialogs = ['^' + ' '.join(dia.split()) for dia in dialogs]
    debug = 'MATCHING: {}\n'.format(sentence)
    for index, regex in enumerate(dialogs):
        match = re.match(regex, sentence)
        debug += '---------------\n'
        debug += '{} {}\n'.format(regex, match is not None)
        if match:
            return index, debug
    else:
        return False, debug


@given('an english speaking user')
def given_english(context):
    context.lang = 'en-us'


@when('the user says "{text}"')
def when_user_says(context, text):
    context.bus.emit(Message('recognizer_loop:utterance',
                             data={'utterances': [text],
                                   'lang': 'en-us',
                                   'session': '',
                                   'ident': time.time()},
                             context={'client_name': 'mycroft_listener'}))


def then_wait(msg_type, then_func, context, timeout=TIMEOUT):
    count = 0
    debug = ''
    while count < TIMEOUT:
        for message in context.bus.get_messages(msg_type):
            status, test_dbg = then_func(message)
            debug += test_dbg
            if status:
                context.matched_message = message
                return True, debug
        time.sleep(1)
        count += 1
    # Timed out return debug from test
    return False, debug


def print_mycroft_responses(context):
    messages = context.bus.get_messages('speak')
    if len(messages) > 0:
        print('Mycroft responded with:')
        for m in messages:
            print('Mycroft: "{}"'.format(m.data['utterance']))


@then('"{skill}" should reply with dialog from "{dialog}"')
def then_dialog(context, skill, dialog):
    def check_dialog(message):
        utt_dialog = message.data.get('meta', {}).get('dialog')
        return (utt_dialog == dialog.replace('.dialog', ''), '')

    passed, debug = then_wait('speak', check_dialog, context)
    if not passed:
        print(debug)
        print_mycroft_responses(context)

    assert passed


@then('"{skill}" should reply with "{example}"')
def then_example(context, skill, example):
    skill_path = context.msm.find_skill(skill).path
    dialog = dialog_from_sentence(example, skill_path)
    print('Matching with the dialog file: {}'.format(dialog))
    assert dialog is not None
    then_dialog(context, skill, dialog)


@then('"{skill}" should reply with anything')
def then_anything(context, skill):
    def check_any_messages(message):
        debug = ''
        result = message is not None
        return (result, debug)

    passed = then_wait('speak', check_any_messages, context)
    if not passed:
        print('No speech recieved at all.')
    assert passed


@then('"{skill}" should reply with exactly "{text}"')
def then_exactly(context, skill, text):
    def check_exact_match(message):
        utt = message.data['utterance'].lower()
        debug = 'Comparing {} with expected {}\n'.format(utt, text)
        result = utt == text.lower()
        return (result, debug)

    passed, debug = then_wait('speak', check_exact_match, context)
    if not passed:
        print(debug)
        print_mycroft_responses(context)
    assert passed


@then('mycroft reply should contain "{text}"')
def then_contains(context, text):
    def check_contains(message):
        utt = message.data['utterance'].lower()
        debug = 'Checking if "{}" contains "{}"\n'.format(utt, text)
        result = text.lower() in utt
        return (result, debug)

    passed, debug = then_wait('speak', check_contains, context)

    if not passed:
        print('No speech contained the expected content')
        print_mycroft_responses(context)
    assert passed


@then('the user says "{text}"')
def then_user_follow_up(context, text):
    time.sleep(2)
    wait_while_speaking()
    context.bus.emit(Message('recognizer_loop:utterance',
                             data={'utterances': [text],
                                   'lang': 'en-us',
                                   'session': '',
                                   'ident': time.time()},
                             context={'client_name': 'mycroft_listener'}))
