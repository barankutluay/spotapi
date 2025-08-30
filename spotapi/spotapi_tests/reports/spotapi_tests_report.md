### Integration Album Info

| Metric | Value |
|--------|-------|
| Tracks Count | 10 |

Integration pagination yielded 1 batch(es).

### Album Initialization

| Metric | Value |
|--------|-------|
| Album ID | testid |
| Album Link | https://open.spotify.com/album/testid |
| Base Client | BaseClient |

### Album Query Structure
sss
| Metric | Value |
|--------|-------|
| operationName | str |
| variables | str |
| extensions | str |

_validate_response accepted a valid mapping.

_validate_response raised AlbumError for invalid response.

### Get Album Info

| Metric | Value |
|--------|-------|
| Tracks Count | 0 |

get_album_info raised AlbumError on failure response.

### Paginate Album Batches

| Metric | Value |
|--------|-------|
| Number of Batches | 3 |

### Artist Initialization

| Metric | Value |
|--------|-------|
| Requires Login | False |
| Base Client | BaseClient |

### Query Artists

| Metric | Value |
|--------|-------|
| Artists Count | 0 |

query_artists raised ArtistError on failure response.

### Get Artist

| Metric | Value |
|--------|-------|
| Artist Name | Test Artist |

get_artist raised ArtistError on failure response.

### Paginate Artists Single Page

| Metric | Value |
|--------|-------|
| Batches | 1 |

### Paginate Artists Multiple Pages

| Metric | Value |
|--------|-------|
| Number of Batches | 2 |

_do_follow success and failure branches tested.

Follow and unfollow methods executed successfully.

Follow/unfollow raised ValueError when login required.

### Integration Artist Info

| Metric | Value |
|--------|-------|
| Artists Count | 10 |

Integration pagination yielded 1 batch(es).

### TOTP Fallback

| Metric | Value |
|--------|-------|
| Version | 18 |
| TOTP | 874088 |

### TOTP Secret Fetch

| Metric | Value |
|--------|-------|
| Version | 18 |
| Secret Bytes | [1, 2, 3] |

### Creator Defaults

| Metric | Value |
|--------|-------|
| Email | pKhvlfyRWA@yandex.com |
| Password length | 12 |
| Display Name | ezdBKYnrVE |
| Birthdate | 1971-10-22 |
| Submission ID | b9a83f7e-a2fc-44ba-90e6-66c35d1b3d4f |

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

### JoinFamily Init

| Metric | Value |
|--------|-------|
| address | 123 Fake St |
| invite_token | invite_abc123 |
| session_id | 71916315-7de9-46fa-80d7-dad593947ca0 |

### Get Session

| Metric | Value |
|--------|-------|
| csrf | csrf_val |

Get session failed as expected.

### Autocomplete Result

| Metric | Value |
|--------|-------|
| addresses_count | 2 |
| csrf | new_csrf |

Autocomplete failed as expected.

### Try Address Success

| Metric | Value |
|--------|-------|
| ok | True |
| csrf | csrf_upd |

### Try Address Fail

| Metric | Value |
|--------|-------|
| ok | False |
| csrf | csrf_upd |

### Get Address

| Metric | Value |
|--------|-------|
| selected_place_id | g_b |

No candidate could be confirmed; raised FamilyError as expected.

### Add To Family Call

| Metric | Value |
|--------|-------|
| url_called | https://www.spotify.com/api/family/v1/family/member/ |

Add to family failed as expected.

add_to_family full flow executed.

### Family Home

| Metric | Value |
|--------|-------|
| members_count | 1 |

get_family_home failure raised FamilyError as expected.

get_family_home invalid json raised FamilyError as expected.

### Members Cache

| Metric | Value |
|--------|-------|
| first | [1, 2, 3] |
| second | [1, 2, 3] |

### Enough Space - Case 1

| Metric | Value |
|--------|-------|
| members | 3 |

### Enough Space - Case 2

| Metric | Value |
|--------|-------|
| members | 6 |

Family init raised ValueError for non-premium user as expected.

### Family Init Premium

| Metric | Value |
|--------|-------|
| _user_family_is_none | True |

Integration flow: Login.login() executed successfully.

### Login Initialization

| Metric | Value |
|--------|-------|
| Identifier | user@example.com |
| Password | password123 |
| Logged In | False |

### Login from_cookies

| Metric | Value |
|--------|-------|
| Logged In | True |

Login from_saver loaded successfully.

_submit_password executed successfully.

Login raised LoginError due to missing solver.

handle_login_error raised LoginError as expected.

Full login flow executed successfully.

_submit_challenge executed successfully.

