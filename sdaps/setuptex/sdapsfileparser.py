# -*- coding: utf-8 -*-
# SDAPS - Scripts for data acquisition with paper based surveys
# Copyright(C) 2008, Christoph Simon <post@christoph-simon.eu>
# Copyright(C) 2008, Benjamin Berg <benjamin@sipsolutions.net>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from sdaps import log
import xml.sax
import zipfile
import re

from sdaps import model
from sdaps.utils.latex import latex_to_unicode

QOBJECT_PREFIX = u'QObject'
ANSWER_PREFIX = u'Answer'
BOX = u'Box'
TEXTBOX = u'Textbox'
RANGE_PREFIX = u'Range'

index_re = re.compile(r'''^(?P<index>(?:[0-9]+\.)+)(?P<string>.*)$''')


def get_index_and_string(string):
    match = index_re.match(string)
    if match is None:
        if string.startswith('XAUTO. '):
            return None, string[7:]
        return None, string

    string = match.group('string')
    index = match.group('index')
    index = index.split('.')[:-1]
    index = tuple([int(x) for x in index])

    return index, string

def parse(survey):

    sdaps_file = open(survey.path('questionnaire.sdaps'))
    # the file is encoded in ascii format
    sdaps_data = sdaps_file.read().decode('utf-8')
    qobject = None
    auto_numbering_id = (0,)

    for line in sdaps_data.split('\n'):
        line = line.strip()
        if line == "":
            continue
        arg, value = line.split('=', 1)
        arg = arg.strip()
        value = value.strip()
        value = latex_to_unicode(value)

        if arg == 'Title':
            survey.title = value
        elif arg == 'PrintQuestionnaireId':
            survey.defs.print_questionnaire_id = bool(int(value))
        elif arg == 'PrintSurveyId':
            survey.defs.print_survey_id = bool(int(value))
        elif arg == 'Pages':
            survey.questionnaire.page_count = int(value)
        elif arg == 'CheckMode':
            survey.defs.checkmode = value
            assert survey.defs.checkmode in model.survey.valid_checkmodes
        elif arg == 'GlobalID':
            survey.global_id = value
        elif arg == 'GlobalIDLabel':
            # Ignore for now
            pass
        elif arg == 'Duplex':
            survey.defs.duplex = (value == "True")
        elif arg == 'Style':
            survey.defs.style = value
            assert survey.defs.style in model.survey.valid_styles
        elif arg == "PageSize":
            args = value.split(',')
            args = [arg.strip() for arg in args]

            width, height = [round(float(arg[:-2]) / 72.27 * 25.4, 3) for arg in args]

            survey.defs.paper_width = width
            survey.defs.paper_height = height

        elif arg.startswith(QOBJECT_PREFIX):
            index, string = get_index_and_string(value)
            if index:
                auto_numbering_id = index + (0,)
            else:
                auto_numbering_id = auto_numbering_id[:-1] + (auto_numbering_id[-1] + 1,)
                index = auto_numbering_id

            qobject_type = arg[len(QOBJECT_PREFIX) + 1:]

            qobject = getattr(model.questionnaire, qobject_type)
            assert issubclass(qobject, model.questionnaire.QObject)
            qobject = qobject()
            survey.questionnaire.add_qobject(qobject, new_id=index)
            qobject.setup.init()

            qobject.setup.question(string)
        elif arg.startswith(ANSWER_PREFIX):
            assert qobject is not None

            answer_type = arg[len(ANSWER_PREFIX) + 1:]

            qobject.setup.answer(value)

        elif arg.startswith(RANGE_PREFIX):
            assert qobject is not None
            assert isinstance(qobject, model.questionnaire.Range)

            idx, answer = value.split(maxsplit=1)
            idx = int(idx)

            range_type = arg[len(RANGE_PREFIX) + 1:].lower()

            if range_type == u'lower':
                qobject.set_lower(idx, answer)
            elif range_type == u'upper':
                qobject.set_upper(idx, answer)
            else:
                raise AssertionError('File format error, %s has to be either lower or upper!' % RANGE_PREFIX)

        elif arg == BOX:
            args = value.split(',')
            args = [arg.strip() for arg in args]

            boxtype = args[0]
            # Convert to mm
            page = int(args[1])
            x, y, width, height = [float(arg[:-2]) / 72.27 * 25.4 for arg in args[2:6]]
            y = survey.defs.paper_height - y

            if boxtype == 'Textbox':
                box = model.questionnaire.Textbox()
                assert(len(args) == 6)
            else:
                box = model.questionnaire.Checkbox()
                if len(args) == 7:
                    box.form = args[6]
                else:
                    assert(len(args) == 6)

            box.setup.setup(page, x, y, width, height)
            qobject.setup.box(box)
        else:
            # Falltrough, it is some metadata:
            survey.info[arg] = value

    # Force duplex of for one page questionnaires
    if survey.questionnaire.page_count == 1:
        survey.defs.duplex = False

