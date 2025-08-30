### Creator Defaults

| Metric | Value |
|--------|-------|
| Email | dfjcMONmrA@outlook.com |
| Password length | 12 |
| Display Name | HmdBEtKyjd |
| Birthdate | 1985-05-14 |
| Submission ID | c3e0fc04-35b7-435a-ad79-836d2c3f67ea |

### Session Tokens

| Metric | Value |
|--------|-------|
| api_key | key |
| installation_id | inst |
| csrf_token | csrf |
| flow_id | flow |

Session retrieval failed as expected.

### Payload Keys

| Metric | Value |
|--------|-------|
| account_details | dict |
| callback_uri | str |
| client_info | dict |
| tracking | dict |
| recaptcha_token | str |
| submission_id | str |
| flow_id | str |

Challenge handled successfully.

_process_register success path executed.

_post_request success path executed.

_post_request failure raised GeneratorError as expected.

Creator.register() called saver.save() as expected (branch true).

Creator.register() skipped saver.save() as expected (branch false).

Creator.register raised GeneratorError due to missing solver as expected.

Register full flow executed successfully.

Register save success triggered logger.info as expected.

Register save error triggered logger.error as expected.

AccountChallenge._get_session success executed.

_get_session failure raised GeneratorError as expected.

_submit_challenge failure raised GeneratorError as expected.

_submit_challenge success path executed without exception.

_complete_challenge failure raised GeneratorError as expected.

_complete_challenge failure path raised GeneratorError as expected.

AccountChallenge.defeat_challenge raised GeneratorError due to missing solver as expected.

Account challenge defeated successfully.

_complete_challenge executed successfully without exceptions.

