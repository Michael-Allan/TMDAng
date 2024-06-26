#!/usr/bin/env python3
#
# Copyright (C) 2001-2007 Jason R. Mastaler <jason@mastaler.com>
#
# This file is part of TMDA.
#
# TMDA is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.  A copy of this license should
# be included in the file COPYING.
#
# TMDA is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.
#
# You should have received a copy of the GNU General Public License
# along with TMDA; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA


from optparse import OptionParser, make_option

import os
import sys
import stat

from . import Version


# If -S / --vhome-script flag is given on command line, use it to determine the
# virtual user's home directory and set $HOME to that, so that '~' refers to
# the virtual user's home directory and not the domain directory.
def setvuserhomedir(vhomescript):
    """Set $HOME to the recipient's (virtual user) home directory."""
    host = os.environ['HOST']
    parts = os.environ['EXT'].split('-confirm-', 1)[0].split('-')
    cmd = vhomescript + ' "%s"' + ' "%s"' % (host,)
    username = ''
    for part in parts:
        username += part
        fpin = os.popen(cmd % (username,))
        vuserhomedir = fpin.read().strip()
        if fpin.close() is None:
            os.environ['HOME'] = vuserhomedir
            os.chdir(vuserhomedir)
            break
        else:
            username += '-'
    else:  # didn't find username
        sys.exit(0)

# option parsing

opt_desc = "Filter incoming messages on standard input."

opt_list = [
    make_option("-c", "--config-file",
                metavar="FILE", dest="config_file",
                help= \
"""Specify a different configuration file other than ~/.tmda/config"""),

    make_option("-t", "--template-dir",
                metavar="DIR", dest="template_dir",
                help= \
"""Full pathname to a directory containing custom TMDA templates."""),

   make_option("-I", "--filter-incoming-file",
                metavar="FILE", dest="filter_incoming",
                help= \
"""Full pathname to your incoming filter file.  Overrides
FILTER_INCOMING in ~/.tmda/config."""),

    make_option("-e", "--environ",
                metavar="VAR=VAL", dest="environ", action="append",
                help= \
"""Add an environment variable on the command line.  VAR is the name
of the variable, and VAL, separated by an '=', is its value.  There
should be no whitespace before or after the '='."""),

    make_option("-d", "--discard",
                action="store_true", dest="discard",
                help= \
"""Discard message if address is invalid instead of bouncing it."""),

    make_option("-p", "--print",
                action="store_true", default=False, dest="act_as_filter",
                help= \
"""Print the message to stdout.  This option is useful when TMDA is
run as a filter in maildrop or procmail.  It overrides all other
delivery options, even if a specific delivery is given in a matching
rule. If the message is delivered, TMDA's exit code is 0.  If the
message is dropped, bounced or a confirmation request is sent, the
exit code will be 99.  You can use the exit code in maildrop/procmail
to decide if you want to perform further processing."""),

    make_option("-S", "--vhome-script",
                metavar="SCRIPT", dest="vhomescript",
                help= \
"""Full pathname of SCRIPT that prints a virtual email user's home
directory on standard output.  tmda-filter will read that path and set
$HOME to that path so that '~' expansion works properly for virtual
users.  The script takes two arguments, the user name and the domain,
on its command line.  This option is for use only with the VPopMail
and VMailMgr add-ons to qmail.  See the contrib/ directory for
sample scripts."""),

    make_option("-M", "--filter-match",
                nargs=2, metavar="RECIP SENDER", dest="filter_match",
                help= \
"""Check whether the given e-mail addresses matches a line in your
incoming filter and then exit. The first address given should be the
message recipient (you), and the second is the sender. This option
will also check for parsing errors in the filter file."""),

    make_option("-V",
                action="store_true", default=False, dest="full_version",
                help="show full TMDA version information and exit"),
    ]

parser = OptionParser(option_list=opt_list, description=opt_desc,
                      version=Version.TMDA)
(opts, args) = parser.parse_args()

if opts.full_version:
    print(Version.ALL)
    sys.exit()
if opts.config_file:
    os.environ['TMDARC'] = opts.config_file
if opts.template_dir:
    os.environ['TMDA_TEMPLATE_DIR'] = opts.template_dir
if opts.filter_incoming:
    os.environ['TMDA_FILTER_INCOMING'] = opts.filter_incoming
if opts.environ:
    for pair in opts.environ:
        try:
            key, value = pair.split('=', 1)
            os.environ[key] = value
        except (KeyError, ValueError):
            parser.error('bad environment key-value pair - "%s"' % pair)
if opts.vhomescript and 'EXT' in os.environ and 'HOST' in os.environ:
    setvuserhomedir(opts.vhomescript)


# Defer the delivery if the sticky bit is set on $HOME (chmod +t).
# This allows users and processes to safely edit the contents of
# ~/.tmda/.  Remove sticky bit with chmod -t $HOME.  This idea comes
# from qmail.  Check for the sticky bit here, after $HOME is set for
# virtual users, but before Defaults is imported.
homestat = os.stat(os.path.expanduser('~'))
homesticky = homestat[stat.ST_MODE] & stat.S_ISVTX
if homesticky:
    sys.stdout.write('tmda-filter: home directory is sticky.')
    sys.exit(75)


from . import Defaults
from . import Address
from . import Cookie
from . import Errors
from . import FilterParser
from . import MTA
from . import Util
from .Queue.Queue import Queue

from email.utils import parseaddr, getaddresses
import fileinput
import time


# Just check Defaults.FILTER_INCOMING for syntax errors and possible
# matches, and then exit.
if opts.filter_match:
    sender = opts.filter_match[-1]
    recip = opts.filter_match[-2]
    Util.filter_match(Defaults.FILTER_INCOMING, recip, sender)
    sys.exit()

if opts.act_as_filter:
    Defaults.DELIVERY = '_filter_'

TIME = time.time()
TIMESTAMP = str('%d' % TIME)
MAILID = "%s.%s" % (TIMESTAMP, Defaults.PID)

# A pending queue instance
Q = Queue()
Q = Q.init()

# We use this MTA instance to control the fate of the message.
mta = MTA.init(Defaults.MAIL_TRANSFER_AGENT, Defaults.DELIVERY)

# Read sys.stdin into a temporary variable for later access.
from io import BytesIO
stdin = BytesIO(sys.stdin.buffer.read())

# The incoming message as an email.Message object.
msgin = Util.msg_from_file(stdin, isBytes=True)

# Original message contents as a string.
orig_msgin_as_string = Util.msg_as_string(msgin)

# Original message headers as a string.
orig_msgin_headers_as_string = Util.headers_as_string(msgin)

# Original message headers as a raw string.
orig_msgin_headers_as_raw_string = Util.headers_as_raw_string(msgin)

# Original message body.
orig_msgin_body = msgin.get_payload()

# Original message body as a raw string.
orig_msgin_body_as_raw_string = Util.body_as_raw_string(msgin)

# Calculate the incoming message size.
orig_msgin_size = len(orig_msgin_as_string)

# Collect the three essential environment variables, and defer if they
# are missing.

# SENDER is the envelope sender address.
envelope_sender = os.environ.get('SENDER')
if envelope_sender == None:
    raise Errors.MissingEnvironmentVariable('SENDER')
# RECIPIENT is the envelope recipient address.
# Use Defaults.RECIPIENT_HEADER instead if set.
recipient_header = None
if Defaults.RECIPIENT_HEADER:
    recipient_header = parseaddr(msgin.get(Defaults.RECIPIENT_HEADER))[1]
envelope_recipient = (recipient_header or os.environ.get('RECIPIENT'))
if envelope_recipient == None:
    raise Errors.MissingEnvironmentVariable('RECIPIENT')
# EXT is the recipient address extension.
address_extension = (os.environ.get('EXT')           # qmail
                     or os.environ.get('EXTENSION')) # Postfix
# Extract EXT from Defaults.RECIPIENT_HEADER if it isn't set.
if not address_extension and (Defaults.RECIPIENT_HEADER and recipient_header):
    recip = recipient_header.split('@')[0]       # remove domain
    if recip:
        pieces = recip.split(Defaults.RECIPIENT_DELIMITER, 1)
        if len(pieces) > 1:
            address_extension = pieces[1]

# If SENDER exists but its value is empty, the message has an empty
# envelope sender.  Set it to the string '<>' so it can be matched as
# such in the filter files.
if envelope_sender == '':
    envelope_sender = '<>'
# If running Sendmail, make sure envelope_sender contains a fully
# qualified address by appending the local hostname if necessary.
# This is often the case when the message is sent between local users
# on a Sendmail system.
elif (Defaults.MAIL_TRANSFER_AGENT == 'sendmail' and
      len(envelope_sender.split('@')) == 1):
    envelope_sender = envelope_sender + '@' + Util.gethostname()
# Ditto for envelope_recipient
if (Defaults.MAIL_TRANSFER_AGENT == 'sendmail' and
    len(envelope_recipient.split('@')) == 1):
    envelope_recipient = envelope_recipient + '@' + Util.gethostname()

# recipient_address is the original address the message was sent to,
# not qmail-send's rewritten interpretation.  This will be the same as
# envelope_recipient if we are not running under a qmail virtualdomain.
recipient_address = envelope_recipient
if (Defaults.MAIL_TRANSFER_AGENT == 'qmail' and
    Defaults.USEVIRTUALDOMAINS and
    os.path.exists(Defaults.VIRTUALDOMAINS)):
    # Parse the virtualdomains control file; see qmail-send(8) for
    # syntax rules.  All this because qmail doesn't store the original
    # envelope recipient in the environment.
    ousername, odomain = envelope_recipient.split('@', 1)
    for line in fileinput.input(Defaults.VIRTUALDOMAINS):
        vdomain_match = 0
        line = line.strip().lower()
        # Comment or blank line?
        if line == '' or line[0] in '#':
            continue
        else:
            vdomain, prepend = line.split(':', 1)
            # domain:prepend
            if vdomain == odomain.lower():
                vdomain_match = 1
            # .domain:prepend (wildcard)
            elif not vdomain.split('.', 1)[0]:
                if odomain.lower().find(vdomain) != -1:
                    vdomain_match = 1
            # user@domain:prepend
            else:
                try:
                    if vdomain.split('@', 1)[1] == odomain.lower():
                        vdomain_match = 1
                except IndexError:
                    pass
            if vdomain_match:
                # strip off the prepend
                if prepend:
                    nusername = ousername.replace(prepend + '-', '', 1)
                    recipient_address = nusername + '@' + odomain
                    # also strip off the prepend and the virtual
                    # username from address_extension
                    address_extension = (Defaults.RECIPIENT_DELIMITER.join
                                         (nusername.split
                                          (Defaults.RECIPIENT_DELIMITER, 1)[1:]))
                    fileinput.close()
                    break

os.environ['TMDA_RECIPIENT'] = recipient_address

# Collect some header values for later use.
subject = msgin.get('subject')
x_primary_address = parseaddr(msgin.get('x-primary-address'))[1]

# Catchall variable to enable/disable auto-responses.
auto_reply = 1


###########
# Functions
###########

def logit(action, msg):
    """Write delivery statistics to the logfile if it's enabled."""
    if action in ('DELIVER', 'OK') and Defaults.DELIVERY == '_filter_':
        action += ' [filtered to stdout]'
    action_msg = action + ' ' + msg
    if not recipient_address:
        return
    if Defaults.LOGFILE_INCOMING:
        from . import MessageLogger
        logger = MessageLogger.MessageLogger(Defaults.LOGFILE_INCOMING,
                                             msgin,
                                             envsender = envelope_sender,
                                             envrecip = recipient_address,
                                             msg_size = orig_msgin_size,
                                             action_msg = action_msg)
        logger.write()
    if Defaults.ACTION_HEADER_INCOMING:
        del msgin['X-TMDA-Action']
        msgin['X-TMDA-Action'] = action_msg


def autorespond_to_sender(sender):
    """Return true if TMDA should auto-respond to this sender."""
    # Try and detect a bounce message.
    if envelope_sender == '<>' or \
           envelope_sender == '#@[]' or \
           envelope_sender.lower().startswith('mailer-daemon'):
        logit('NOREPLY', '(envelope sender = %s)' % envelope_sender)
        return False
    # Majordomo messages don't give any indication that they are
    # auto-responses. tsk, tsk.
    if envelope_sender.lower().startswith('majordomo'):
        logit('NOREPLY', '(Majordomo)')
        return False
    # Try and detect an auto-response.
    guilty_header = None
    auto_submitted = msgin.get('auto-submitted')
    if auto_submitted:
        if auto_submitted.lower().strip().startswith('auto-generated') or \
               auto_submitted.lower().strip().startswith('auto-replied'):
            guilty_header = 'Auto-Submitted: %s' % auto_submitted
    # Try and detect a mailing list message by looking for
    # characteristic header fields.
    if guilty_header is None:
        list_headers = ['List-Id', 'List-Help', 'List-Subscribe',
                        'List-Unsubscribe', 'List-Post', 'List-Owner',
                        'List-Archive', 'Mailing-List', 'X-Mailing-List',
                        'X-ML-Name', 'X-List']
        for hdr in list_headers:
            if hdr in msgin:
                guilty_header = '%s: %s' % (hdr, msgin.get(hdr))
                break
    # "Precedence:" value junk, bulk, or list
    if guilty_header is None:
        precedence = msgin.get('precedence')
        if precedence and precedence.lower() in ('bulk', 'junk', 'list'):
            guilty_header = 'Precedence: %s' % precedence
    if guilty_header:
        logit('NOREPLY', '(%s)' % guilty_header)
        return False
    # The above methods have been verified to detect list messages
    # from the following mailing list management packages/services:
    #
    # communigate pro, ecartis, ezmlm, fml, listar, listbox.com,
    # listguru, listproc, lyris, mailman, majordomo, minimalist,
    # smartlist, sympa, topica, yahoogroups
    #
    # Auto-response rate limiting.  Algorithm based on Bruce Guenter's
    # qmail-autoresponder (http://untroubled.org/qmail-autoresponder/).
    # See qmail-autoresponder(1) for more details.
    if Defaults.MAX_AUTORESPONSES_PER_DAY == 0:
        return True
    if os.path.isdir(Defaults.RESPONSE_DIR):
        os.chdir(Defaults.RESPONSE_DIR)
        files = os.listdir('.')
        sndrlist = []
        for file in files:
            # Ignore foreign files.
            try:
                timestamp, pid, address = file.split('.', 2)
            except ValueError:
                continue
            # If file is more than one day old, delete it and continue.
            now = int(time.time())
            if now > (int(timestamp) + Util.seconds('1d')):
                try:
                    os.unlink(file)
                except OSError:
                    # ignore errors on unlink
                    pass
                continue
            else:
                sndrlist.append(address)
        # Count remaining occurrences of this sender, and don't
        # respond if that number it exceeds our threshold.
        if sndrlist.count(Util.normalize_sender(sender)) >= \
               Defaults.MAX_AUTORESPONSES_PER_DAY:
            logit('NOREPLY',
                  '(%s = %s)' % ('MAX_AUTORESPONSES_PER_DAY',
                                 Defaults.MAX_AUTORESPONSES_PER_DAY))
            return False
    return True


def send_bounce(bounce_message, type):
    """Send a auto-response back to the envelope sender address."""
    if autorespond_to_sender(envelope_sender) and auto_reply:
        from . import AutoResponse
        ar = AutoResponse.AutoResponse(msgin, bounce_message,
                                       type, envelope_sender)
        ar.create()
        ar.send()
        # Optionally, record this auto-response.
        if Defaults.MAX_AUTORESPONSES_PER_DAY != 0:
            ar.record()


def send_cc(address):
    """Send a 'carbon copy' of the message to address."""
    Util.sendmail(Util.msg_as_string(msgin), address, envelope_sender)
    logit('CC', address)


def do_default_action(action, logname, template=None):
    """Handle ACTION_* actions"""
    if action in ('bounce', 'reject'):
        logit('BOUNCE', logname)
        bouncegen('bounce', template=template)
    elif action in ('drop', 'exit', 'stop'):
        logit('DROP', logname)
        mta.stop()
    elif action in ('accept', 'deliver', 'ok'):
        logit('OK', logname)
        mta.deliver(msgin)
    elif action == 'hold':
        logit('HOLD', logname)
        bouncegen('hold')
    else:
        logit('CONFIRM', logname)
        bouncegen('request')



def release_pending(timestamp, pid, msg):
    """Release a confirmed message from the pending queue."""
    # Remove Return-Path: to avoid duplicates.
    return_path = return_path = parseaddr(msg.get('return-path'))[1]
    del msg['return-path']
    # Remove X-TMDA-Recipient:
    recipient = msg.get('x-tmda-recipient')
    del msg['x-tmda-recipient']
    # To avoid a mail loop on re-injection, prepend an ``Old-'' prefix
    # to all existing Delivered-To lines.
    Util.rename_headers(msg, 'Delivered-To', 'Old-Delivered-To')
    # Add an X-TMDA-Confirm-Done: field to the top of the header for
    # later verification.  This includes a timestamp, pid, and HMAC.
    del msg['X-TMDA-Confirm-Done']
    msg['X-TMDA-Confirm-Done'] = Cookie.make_confirm_cookie(timestamp,
                                                            pid, 'done')
    # Add the date when confirmed in a header.
    del msg['X-TMDA-Confirmed']
    msg['X-TMDA-Confirmed'] = Util.make_date()
    # Reinject the message to the original envelope recipient.
    Util.sendmail(Util.msg_as_string(msg), recipient, return_path)
    mta.stop()


def verify_confirm_cookie(confirm_cookie, confirm_action):
    """Verify a confirmation cookie."""
    # Save some time if the cookie is bogus.
    try:
        confirm_timestamp, confirm_pid, confirm_hmac = \
                           confirm_cookie.split('.')
    except ValueError:
        do_default_action(Defaults.ACTION_INVALID_CONFIRMATION.lower(),
                          'action_invalid_confirmation',
                          'bounce_invalid_confirmation.txt')
    confirmed_mailid = '%s.%s' % (confirm_timestamp, confirm_pid)
    # pre-confirmation
    if confirm_action == 'accept':
        new_confirm_hmac = Cookie.confirmationmac(confirm_timestamp,
                                                  confirm_pid, confirm_action)
        # Accept the message only if the HMAC can be verified and the
        # message exists in the pending queue.
        if not (confirm_hmac == new_confirm_hmac):
            do_default_action(Defaults.ACTION_INVALID_CONFIRMATION.lower(),
                              'action_invalid_confirmation',
                              'bounce_invalid_confirmation.txt')
        elif not (Q.find_message(confirmed_mailid)):
            do_default_action(Defaults.ACTION_MISSING_PENDING.lower(),
                              'action_missing_pending',
                              'bounce_missing_pending.txt')
        else:
            msg = Q.fetch_message(confirmed_mailid)
            logit("CONFIRM", "accept " + confirmed_mailid)
            # Optionally append the sender's address to a file and/or DB.
            if Defaults.CONFIRM_APPEND or Defaults.DB_CONFIRM_APPEND:
                confirm_append_addr = Util.confirm_append_address(
                    parseaddr(msg.get('x-primary-address'))[1],
                    parseaddr(msg.get('return-path'))[1])
                if not confirm_append_addr:
                    raise IOError(confirmed_mailid + ' has no Return-Path header!')
                if Defaults.CONFIRM_APPEND:
                    if Util.append_to_file(confirm_append_addr,
                                           Defaults.CONFIRM_APPEND) != 0:
                        logit('CONFIRM_APPEND', Defaults.CONFIRM_APPEND)
                if Defaults.DB_CONFIRM_APPEND and Defaults.DB_CONNECTION:
                    _username = Defaults.USERNAME.lower()
                    _hostname = Defaults.HOSTNAME.lower()
                    _recipient = _username + '@' + _hostname
                    params = FilterParser.create_sql_params(
                        recipient=_recipient, username=_username,
                        hostname=_hostname, sender=confirm_append_addr)
                    Util.db_insert(Defaults.DB_CONNECTION,
                                   Defaults.DB_CONFIRM_APPEND,
                                   params)
                    logit('DB_CONFIRM_APPEND', '')
            # Optionally carbon copy the confirmation to another address.
            if Defaults.CONFIRM_ACCEPT_CC:
                send_cc(Defaults.CONFIRM_ACCEPT_CC)
            # Optionally generate a confirmation acceptance notice.
            if Defaults.CONFIRM_ACCEPT_NOTIFY:
                bouncegen('accept', template='confirm_accept.txt')
            # Release the message for delivery if we get this far.
            release_pending(confirm_timestamp, confirm_pid, msg)
    # post-confirmation
    elif confirm_action == 'done':
        # Regenerate the HMAC for comparison.
        new_confirm_hmac = Cookie.confirmationmac(confirm_timestamp,
                                                  confirm_pid, 'done')
        # Accept the message only if the HMAC can be verified.
        if not (confirm_hmac == new_confirm_hmac):
            # Ask for confirmation instead of bouncing or dropping the
            # message in case the sender inadvertently had an
            # X-TMDA-Confirm-Done field in this message, such as when
            # redirecting a previously confirmed message.
            logit("CONFIRM", "bad_confirm_done_cookie")
            bouncegen('request')
        else:
            logit("OK", "good_confirm_done_cookie")
            try:
                Q.delete_message(confirmed_mailid)
            except OSError:
                pass
            # Remove X-TMDA-Confirm-Done: since it's only used
            # internally.  This won't work when delivering '_qok_',
            # since another program (qmail-local) is doing the actual
            # writing of the message but we try anyway.
            del msgin['x-tmda-confirm-done']
            mta.deliver(msgin)


def dispose_expired_dated(cookie_date):
    """Dispose of an expired dated address based on ACTION_EXPIRED_DATED
    dictionary settings"""
    templist = []
    havedefault = False
    # go through all of the times, and convert them into seconds
    # default becomes "0", saving the symbolic name logging
    for k,v in Defaults.ACTION_EXPIRED_DATED.iteritems():
        if k != 'default':
            templist.append((Util.seconds(k),v,k))
        else:
            # Default is False.  The number represents the number of
            # seconds that the address has been expired.  A negative
            # number would imply a non-expired address, so zero will
            # suffice as a default.
            templist.append((0,v,k))
            havedefault = True
    # If no default specfied, assume "confirm"
    if havedefault is False:
        templist.append((0,'confirm','default'))
    templist.sort()
    templist.reverse()
    # calculate how long ago the address expired
    overdue = int('%d' % time.time()) - int(cookie_date)
    # Figure out which action should be used.  Since the list is reverse
    # sorted, the first time that overdue is > then the time in the list
    # means that we've found the action to use
    for i in templist:
        if overdue > i[0]:
            logmsg = "ACTION_EXPIRED_DATED/%s (%s)" % \
                (i[2], Util.make_date(int(cookie_date)))
            do_default_action(i[1].lower(), logmsg, 'bounce_expired_dated.txt')


def verify_dated_cookie(dated_cookie):
    """Verify a dated cookie."""
    # Save some time if the cookie is bogus.
    try:
        cookie_date, datemac = dated_cookie.split('.')
    except ValueError:
        do_default_action(Defaults.ACTION_FAIL_DATED.lower(),
                          'action_fail_dated',
                          'bounce_fail_dated.txt')
    # Accept the message only if the address has not expired, and the
    # HMAC is valid.
    if datemac != Cookie.datemac(cookie_date):
        do_default_action(Defaults.ACTION_FAIL_DATED.lower(),
                          'action_fail_dated',
                          'bounce_fail_dated.txt')
    else:
        if int(cookie_date) >= int('%d' % time.time()):
            logit("OK", "good_dated_cookie (%s)" % \
                  Util.make_date(int(cookie_date)))
            mta.deliver(msgin)
        else:
            logmsg = "ACTION_EXPIRED_DATED (%s)" % \
                Util.make_date(int(cookie_date))
            if type(Defaults.ACTION_EXPIRED_DATED) is str:
                do_default_action(Defaults.ACTION_EXPIRED_DATED.lower(),
                                  logmsg, 'bounce_expired_dated.txt')
            elif type(Defaults.ACTION_EXPIRED_DATED) is not dict:
                errmsg = 'ACTION_EXPIRED_DATED is wrong type (%s). ' % \
                    type(Defaults.ACTION_EXPIRED_DATED)
                raise TypeError(errmsg + 'Must be string or dictionary')
            else:
                dispose_expired_dated(cookie_date)


def verify_sender_cookie(sender_address,sender_cookie):
    """Verify a sender cookie."""
    try:
        addr = Address.Factory(envelope_recipient)
        addr.verify(sender_address)
        logit("OK", "good_sender_cookie")
        mta.deliver(msgin)
    except Address.AddressError:
        do_default_action(Defaults.ACTION_FAIL_SENDER.lower(),
                          'action_fail_sender',
                          'bounce_fail_sender.txt')


def verify_keyword_cookie(keyword_cookie):
    """Verify a keyword cookie."""
    parts = keyword_cookie.split('.')
    keyword = '.'.join(parts[:-1])
    mac = parts[-1:][0]
    newmac = Cookie.make_keywordmac(keyword)
    # Accept the message only if the HMAC can be verified.
    if mac == newmac:
        logit("OK", "good_keyword_cookie \"" + keyword + "\"")
        mta.deliver(msgin)
    else:
        do_default_action(Defaults.ACTION_FAIL_KEYWORD.lower(),
                          'action_fail_keyword',
                          'bounce_fail_keyword.txt')



def bouncegen(mode, template=None):
    """Bounce a message back to sender."""
    # Stop right away if --discard was specified.
    if opts.discard:
        mta.stop()
    # Common variables.
    recipient_address = globals().get('recipient_address')
    recipient_local, recipient_domain = recipient_address.split('@', 1)
    envelope_sender = globals().get('envelope_sender')
    x_primary_address = globals().get('x_primary_address')
    confirm_append_address = Util.confirm_append_address(x_primary_address,
                                                         envelope_sender)
    subject = globals().get('subject')
    original_message_body = globals().get('orig_msgin_body_as_raw_string')
    original_message_headers = globals().get('orig_msgin_headers_as_raw_string')
    original_message_size = globals().get('orig_msgin_size')
    original_message = globals().get('orig_msgin_as_string')
    pending_lifetime = Util.format_timeout(Defaults.PENDING_LIFETIME)
    # Optional 'dated' address variables.
    if Defaults.DATED_TEMPLATE_VARS:
        dated_timeout = Util.format_timeout(Defaults.DATED_TIMEOUT)
        dated_expire_date = time.asctime(time.gmtime
                                         (TIME +
                                          Util.seconds(Defaults.DATED_TIMEOUT)))
        dated_recipient_address = Cookie.make_dated_address(recipient_address)
    # Optional 'sender' address variables.
    if Defaults.SENDER_TEMPLATE_VARS:
        sender_recipient_address = Cookie.make_sender_address(recipient_address,
                                                              envelope_sender)
    if mode == 'accept':                # confirmation acceptance notices
        # assume we are being passed a templatefile
        templatefile = template
    elif mode == 'bounce':              # failure notices
        # assume we are being passed a templatefile
        templatefile = template
    elif mode == 'request':               # confirmation requests
        if template:
            templatefile = template
        else:
            templatefile = 'confirm_request.txt'

        confirm_accept_address = Cookie.make_confirm_address(recipient_address,
                                                             TIMESTAMP,
                                                             Defaults.PID,
                                                             'accept')
        if Defaults.CGI_URL:
            # create the url for tmda-cgi release.
            if Defaults.CGI_VIRTUALUSER:
                # include the current uid, recipient address, and release cookie.
                confirm_accept_url = '%s?%s&%s&%s' %(Defaults.CGI_URL,
                                                     os.geteuid(),
                                                     recipient_address,
                                                     Cookie.make_confirm_cookie(
                    TIMESTAMP,
                    Defaults.PID,
                    'accept'
                    ))
            else:
                # include the current euid and release cookie.
                confirm_accept_url = '%s?%s.%s' %(Defaults.CGI_URL, os.geteuid(),
                                                  Cookie.make_confirm_cookie(TIMESTAMP,
                                                                             Defaults.PID,
                                                                             'accept'))
        Q.insert_message(msgin, MAILID, recipient_address)
    elif mode == 'hold':
        Q.insert_message(msgin, MAILID, recipient_address)
        # Don't send anything for silently held messages
        if Defaults.CONFIRM_CC:
            send_cc(Defaults.CONFIRM_CC)
        logit("HOLD", "pending " + MAILID)
        mta.stop()
    # Create the confirm message and then send it.
    bounce_message = Util.maketext(templatefile, vars())
    if mode == 'accept':
        send_bounce(bounce_message, mode)
    elif mode == 'bounce':
        send_bounce(bounce_message, mode)
        mta.stop()
    elif mode == 'request':
        if Defaults.CONFIRM_CC:
            send_cc(Defaults.CONFIRM_CC)
        logit("CONFIRM", "pending " + MAILID)
        send_bounce(bounce_message, mode)
        mta.stop()


######
# Main
######

def main():
    # cleanup the pending queue
    if Defaults.PENDING_CLEANUP_ODDS != 0:
        from random import random
        if random() < float(Defaults.PENDING_CLEANUP_ODDS):
            Q.cleanup()
    # Get the cookie type and value by parsing the extension address.
    ext = address_extension
    cookie_type = cookie_value = None
    if ext:
        ext_split = ext.lower().split(Defaults.RECIPIENT_DELIMITER)
        cookie_value = ext_split[-1]
        if len(ext_split) > 1:
            cookie_type = ext_split[-2]
    # The list of sender e-mail addresses comes from the envelope
    # sender, the "From:" header, the "Reply-To:" header, and possibly
    # the "X-Primary-Address" header.
    senders = { envelope_sender.lower() }
    confirm_append_address = Util.confirm_append_address(x_primary_address,
                                                         envelope_sender)
    if confirm_append_address:
        senders.add(confirm_append_address)
    for a in getaddresses(msgin.get_all('from'    , [])): senders.add(a[1].lower())
    for a in getaddresses(msgin.get_all('reply-to', [])): senders.add(a[1].lower())

    sender_list = list(senders)
    # Process confirmation messages first.
    confirm_done_hdr = msgin.get('x-tmda-confirm-done')
    if confirm_done_hdr:
        verify_confirm_cookie(confirm_done_hdr, 'done')
    if (cookie_type in Defaults.TAGS_CONFIRM) and cookie_value:
        verify_confirm_cookie(cookie_value, 'accept')
    # Parse the incoming filter file.
    infilter = FilterParser.FilterParser(Defaults.DB_CONNECTION)
    infilter.read(Defaults.FILTER_INCOMING)
    (actions, matching_line) = infilter.firstmatch(recipient_address,
                                                   sender_list,
                                                   orig_msgin_body_as_raw_string,
                                                   orig_msgin_headers_as_raw_string,
                                                   orig_msgin_size)
    (action, option) = actions.get('incoming', (None, None))
    # Dispose of the message now if there was a filter file match.
    # Log the action along with and the matching line in the filter
    # file that caused it.
    if action in ('bounce','reject'):
        if Defaults.FILTER_BOUNCE_CC:
            send_cc(Defaults.FILTER_BOUNCE_CC)
        if option:
            logit('BOUNCE', '(%s)' % (matching_line + '=' + option))
            bouncegen('bounce', template=option)
        else:
            logit('BOUNCE', '(%s)' % matching_line)
            bouncegen('bounce', 'bounce_incoming.txt')
    elif action in ('drop','exit','stop'):
        if Defaults.FILTER_DROP_CC:
            send_cc(Defaults.FILTER_DROP_CC)
        logit('DROP', '(%s)' % matching_line)
        mta.stop()
    elif action in ('accept','deliver','ok'):
        if option:
            logit('DELIVER', '(%s)' % (matching_line + '=' + option))
            mta.deliver(msgin, option)
        else:
            logit('OK', '(%s)' % matching_line)
            mta.deliver(msgin)
    elif action == 'confirm':
        if option:
            logit('CONFIRM', '(%s)' % (matching_line + '=' + option))
            bouncegen('request', template=option)
        else:
            logit('CONFIRM', '(%s)' % matching_line)
            bouncegen('request')
    elif action == 'hold':
        logit('HOLD', '(%s)' % matching_line)
        bouncegen('hold')
    # The message didn't match the filter file, so check if it was
    # sent to a 'tagged' address.
    # Dated tag?
    if (cookie_type in map(lambda s: s.lower(), Defaults.TAGS_DATED)) \
           and cookie_value:
        verify_dated_cookie(cookie_value)
    # Sender tag?
    elif (cookie_type in map(lambda s: s.lower(), Defaults.TAGS_SENDER)) \
             and cookie_value:
        sender_address = globals().get('envelope_sender')
        verify_sender_cookie(sender_address, cookie_value)
    # Keyword tag?
    elif (cookie_type in map(lambda s: s.lower(), Defaults.TAGS_KEYWORD)) \
             and cookie_value:
        verify_keyword_cookie(cookie_value)
    # If the message gets this far (i.e, was not sent to a tagged
    # address and it didn't match the filter file), then we consult
    # Defaults.ACTION_INCOMING.
    do_default_action(Defaults.ACTION_INCOMING.lower(), 'action_incoming',
                      'bounce_incoming.txt')

# This is the end my friend.
if __name__ == '__main__':
    main()
