import os
from json import dumps, loads

import requests
from apprise import AttachBase, NotifyFormat, NotifyType
from apprise.plugins.NotifyTelegram import NotifyTelegram as NotifyTelegramBase, IS_CHAT_ID_RE

class NotifyTelegram(NotifyTelegramBase):
    def send_media(self, payload, notify_type, attach=None):
        """
        Sends a sticker based on the specified notify type

        """

        # Prepare our Headers
        headers = {
            'User-Agent': self.app_id,
        }

        # Our function name and payload are determined on the path
        function_name = 'SendPhoto'
        key = 'photo'
        path = None

        if isinstance(attach, AttachBase):
            if not attach:
                # We could not access the attachment
                self.logger.error(
                    'Could not access attachment {}.'.format(
                        attach.url(privacy=True)))
                return False

            self.logger.debug(
                'Posting Telegram attachment {}'.format(
                    attach.url(privacy=True)))

            # Store our path to our file
            path = attach.path
            file_name = attach.name
            mimetype = attach.mimetype

            # Process our attachment
            function_name, key = \
                next(((x['function_name'], x['key']) for x in self.mime_lookup
                        if x['regex'].match(mimetype)))  # pragma: no cover

        else:
            attach = self.image_path(notify_type) if attach is None else attach
            if attach is None:
                # Nothing specified to send
                return True

            # Take on specified attachent as path
            path = attach
            file_name = os.path.basename(path)

        url = '%s%s/%s' % (
            self.notify_url,
            self.bot_token,
            function_name,
        )

        # Always call throttle before any remote server i/o is made;
        # Telegram throttles to occur before sending the image so that
        # content can arrive together.
        self.throttle()

        try:
            with open(path, 'rb') as f:
                # Configure file payload (for upload)
                files = {key: (file_name, f)}
                payload['caption'] = payload['text']
                del payload['text']

                self.logger.debug(
                    'Telegram attachment POST URL: %s (cert_verify=%r)' % (
                        url, self.verify_certificate))
                self.logger.debug('Telegram Payload: %s' % str(payload))

                r = requests.post(
                    url,
                    headers=headers,
                    files=files,
                    data=payload,
                    verify=self.verify_certificate,
                    timeout=self.request_timeout,
                )

                if r.status_code != requests.codes.ok:
                    # We had a problem
                    status_str = NotifyTelegram.http_response_code_lookup(r.status_code)

                    self.logger.warning(
                        'Failed to send Telegram attachment: '
                        '{}{}error={}.'.format(
                            status_str,
                            ', ' if status_str else '',
                            r.status_code))

                    self.logger.debug(
                        'Response Details:\r\n{}'.format(r.content))

                    return False

                # Content was sent successfully if we got here
                return True

        except requests.RequestException as e:
            self.logger.warning(
                'A connection error occurred posting Telegram '
                'attachment.')
            self.logger.debug('Socket Exception: %s' % str(e))

        except (IOError, OSError):
            # IOError is present for backwards compatibility with Python
            # versions older then 3.3.  >= 3.3 throw OSError now.

            # Could not open and/or read the file; this is not a problem since
            # we scan a lot of default paths.
            self.logger.error(
                'File can not be opened for read: {}'.format(path))

        return False

    def send(self, body, title='', notify_type=NotifyType.INFO, attach=None,
                body_format=None, **kwargs):
        """
        Perform Telegram Notification
        """

        if len(self.targets) == 0 and self.detect_owner:
            _id = self.detect_bot_owner()
            if _id:
                # Permanently store our id in our target list for next time
                self.targets.append(str(_id))
                self.logger.info(
                    'Update your Telegram Apprise URL to read: '
                    '{}'.format(self.url(privacy=True)))

        if len(self.targets) == 0:
            self.logger.warning('There were not Telegram chat_ids to notify.')
            return False

        headers = {
            'User-Agent': self.app_id,
            'Content-Type': 'application/json',
        }

        # error tracking (used for function return)
        has_error = False

        url = '%s%s/%s' % (
            self.notify_url,
            self.bot_token,
            'sendMessage'
        )

        payload = {
            # Notification Audible Control
            'disable_notification': self.silent,
            # Display Web Page Preview (if possible)
            'disable_web_page_preview': not self.preview,
        }

        # Prepare Message Body
        if self.notify_format == NotifyFormat.MARKDOWN:
            payload['parse_mode'] = 'MARKDOWN'

            payload['text'] = body

        else:  # HTML

            # Use Telegram's HTML mode
            payload['parse_mode'] = 'HTML'
            for r, v, m in self.__telegram_escape_html_entries:

                if 'html' in m:
                    # Handle special cases where we need to alter new lines
                    # for presentation purposes
                    v = v.format(m['html'] if body_format in (
                        NotifyFormat.HTML, NotifyFormat.MARKDOWN) else '')

                body = r.sub(v, body)

            # Prepare our payload based on HTML or TEXT
            payload['text'] = body

        # Create a copy of the chat_ids list
        targets = list(self.targets)
        while len(targets):
            chat_id = targets.pop(0)
            chat_id = IS_CHAT_ID_RE.match(chat_id)
            if not chat_id:
                self.logger.warning(
                    "The specified chat_id '%s' is invalid; skipping." % (
                        chat_id,
                    )
                )

                # Flag our error
                has_error = True
                continue

            if chat_id.group('name') is not None:
                # Name
                payload['chat_id'] = '@%s' % chat_id.group('name')

            else:
                # ID
                payload['chat_id'] = int(chat_id.group('idno'))

            if self.include_image is True:
                # Define our path
                if not self.send_media(payload['chat_id'], notify_type):
                    # We failed to send the image associated with our
                    notify_type
                    self.logger.warning(
                        'Failed to send Telegram type image to {}.',
                        payload['chat_id'])

            if attach:
                # Send our attachments now (if specified and if it exists)
                for attachment in attach:
                    if not self.send_media(
                            payload, notify_type,
                            attach=attachment):

                        # We failed; don't continue
                        has_error = True
                        break

                    self.logger.info(
                        'Sent Telegram attachment: {}.'.format(attachment))

            else:
                # Always call throttle before any remote server i/o is made;
                # Telegram throttles to occur before sending the image so that
                # content can arrive together.
                self.throttle()

                self.logger.debug('Telegram POST URL: %s (cert_verify=%r)' % (
                    url, self.verify_certificate,
                ))
                self.logger.debug('Telegram Payload: %s' % str(payload))

                try:
                    r = requests.post(
                        url,
                        data=dumps(payload),
                        headers=headers,
                        verify=self.verify_certificate,
                        timeout=self.request_timeout,
                    )

                    if r.status_code != requests.codes.ok:
                        # We had a problem
                        status_str = NotifyTelegram.http_response_code_lookup(r.status_code)

                        try:
                            # Try to get the error message if we can:
                            error_msg = loads(r.content).get(
                                'description', 'unknown')

                        except (AttributeError, TypeError, ValueError):
                            # ValueError = r.content is Unparsable
                            # TypeError = r.content is None
                            # AttributeError = r is None
                            error_msg = None

                        self.logger.warning(
                            'Failed to send Telegram notification to {}: '
                            '{}, error={}.'.format(
                                payload['chat_id'],
                                error_msg if error_msg else status_str,
                                r.status_code))

                        self.logger.debug(
                            'Response Details:\r\n{}'.format(r.content))

                        # Flag our error
                        has_error = True
                        continue

                except requests.RequestException as e:
                    self.logger.warning(
                        'A connection error occurred sending Telegram:%s ' % (
                            payload['chat_id']) + 'notification.'
                    )
                    self.logger.debug('Socket Exception: %s' % str(e))

                    # Flag our error
                    has_error = True
                    continue

                self.logger.info('Sent Telegram notification.')



        return not has_error
