import uuid
from typing import Any, List, Mapping, Optional

from spotapi.login import Login
from spotapi.spotapi_exceptions.errors import FamilyError
from spotapi.spotapi_types.annotations import enforce
from spotapi.spotapi_utils.strings import parse_json_string
from spotapi.user import User

__all__ = ["JoinFamily", "Family", "FamilyError"]


@enforce
class JoinFamily:
    """
    Handles joining a Spotify Family plan.

    Attributes:
        user (User): The user attempting to join the family.
        host (Family): The host's family object.
        country (str): Country code for address autocomplete.
        client: HTTP client from Login object.
        family (Mapping[str, Any]): Family home response from host.
        address (str): Host family address.
        invite_token (str): Invitation token for joining the family.
        session_id (str): Unique session identifier for address verification.
        csrf (Optional[str]): CSRF token used in subsequent requests.
        addresses (Optional[List[Mapping[str, Any]]]): Suggested addresses from autocomplete.
    """

    __slots__ = (
        "user",
        "host",
        "country",
        "client",
        "family",
        "address",
        "invite_token",
        "session_id",
        "csrf",
        "addresses",
    )

    JOIN_URL = "https://www.spotify.com/ca-en/family/join/address/{invite_token}/"
    AUTOCOMPLETE_URL = (
        "https://www.spotify.com/api/mup/addresses/v1/address/autocomplete/"
    )
    CONFIRM_ADDRESS_URL = (
        "https://www.spotify.com/api/mup/addresses/v1/user/confirm-user-address/"
    )
    ADD_FAMILY_URL = "https://www.spotify.com/api/family/v1/family/member/"

    def __init__(self, user_login: Login, host: "Family", country: str) -> None:
        """
        Initialize a JoinFamily handler.

        Args:
            user_login (Login): Login instance of the user who will join.
            host (Family): Host family instance to join.
            country (str): Country code for address autocomplete.
        """
        self.user = User(user_login)
        self.host = host
        self.country = country
        self.client = user_login.client

        self.family = self.host.get_family_home()
        self.address = self.family["address"]
        self.invite_token = self.family["inviteToken"]

        self.session_id: str = str(uuid.uuid4())
        self.csrf: Optional[str] = None
        self.addresses: Optional[List[Mapping[str, Any]]] = None

    def _get_session(self) -> None:
        """
        Retrieves a session required for family join flow.

        Raises:
            FamilyError: If session retrieval fails.
        """
        url = self.JOIN_URL.format(invite_token=self.invite_token)
        resp = self.client.get(url)

        if resp.fail:
            raise FamilyError(
                f"Could not get session (status={resp.status_code})",
                error=resp.error.string,
            )

        self.csrf = parse_json_string(resp.response, "csrfToken")

    def _get_autocomplete(self, address: str) -> None:
        """
        Requests address autocomplete suggestions.

        Args:
            address (str): Host's family address.

        Raises:
            FamilyError: If autocomplete request fails.
        """
        payload = {
            "text": address,
            "country": self.country,
            "sessionToken": self.session_id,
        }
        resp = self.client.post(
            self.AUTOCOMPLETE_URL,
            headers={"X-Csrf-Token": self.csrf},
            json=payload,
        )

        if resp.fail:
            raise FamilyError(
                f"Could not get address autocomplete (status={resp.status_code})",
                error=resp.error.string,
            )

        self.addresses = resp.response.get("addresses", [])
        self.csrf = resp.raw.headers.get("X-Csrf-Token")

    def _try_address(self, candidate: Mapping[str, Any]) -> bool:
        """
        Attempts to confirm a suggested address.

        Args:
            candidate (Mapping[str, Any]): Address suggestion.

        Returns:
            bool: True if address confirmed, False otherwise.
        """
        payload = {
            "address_google_place_id": candidate["address"]["googlePlaceId"],
            "session_token": self.session_id,
        }
        resp = self.client.post(
            self.CONFIRM_ADDRESS_URL,
            headers={"X-Csrf-Token": self.csrf},
            json=payload,
        )

        self.csrf = resp.raw.headers.get("X-Csrf-Token")
        return not resp.fail

    def _get_address(self) -> str:
        """
        Retrieves and confirms a valid address for family join.

        Returns:
            str: Confirmed Google Place ID.

        Raises:
            FamilyError: If no valid address can be confirmed.
        """
        self._get_session()
        self._get_autocomplete(self.address)

        for address in self.addresses or []:
            if self._try_address(address):
                return address["address"]["googlePlaceId"]

        raise FamilyError("Could not confirm a valid address")

    def _add_to_family(self, place_id: str) -> None:
        """
        Sends request to add the user to the host family.

        Args:
            place_id (str): Confirmed Google Place ID.

        Raises:
            FamilyError: If addition fails.
        """
        payload = {
            "address": self.address,
            "placeId": place_id,
            "inviteToken": self.invite_token,
        }
        resp = self.client.post(
            self.ADD_FAMILY_URL,
            headers={"X-Csrf-Token": self.csrf},
            json=payload,
        )

        if resp.fail:
            raise FamilyError(
                f"Could not add user to family (status={resp.status_code})",
                error=resp.error.string,
            )

    def add_to_family(self) -> None:
        """
        Executes the full join process:
            1. Retrieve session.
            2. Get and confirm address.
            3. Add user to family.

        Raises:
            FamilyError: If any step fails.
        """
        place_id = self._get_address()
        self._add_to_family(place_id)


@enforce
class Family(User):
    """
    Provides methods for managing a Spotify Family plan.

    Attributes:
        _user_family (Optional[Mapping[str, Any]]): Cached family home data.

    Raises:
        ValueError: If the user does not have premium.
    """

    __slots__ = ("_user_family",)

    HOME_URL = "https://www.spotify.com/api/family/v1/family/home/"

    def __init__(self, login: Login) -> None:
        """
        Initialize a Family handler.

        Args:
            login (Login): Logged-in Login object with premium account.

        Raises:
            ValueError: If the user does not have premium.
        """
        super().__init__(login)

        if not self.has_premium:
            raise ValueError("Must have premium to use Family features")

        self._user_family: Optional[Mapping[str, Any]] = None

    def get_family_home(self) -> Mapping[str, Any]:
        """
        Retrieves family home details.

        Returns:
            Mapping[str, Any]: Family home data.

        Raises:
            FamilyError: If request fails or response is invalid.
        """
        resp = self.login.client.get(self.HOME_URL)

        if resp.fail:
            raise FamilyError(
                f"Could not get family home (status={resp.status_code})",
                error=resp.error.string,
            )

        if not isinstance(resp.response, Mapping):
            raise FamilyError("Invalid JSON structure for family home")

        return resp.response

    @property
    def members(self) -> List[Mapping[str, Any]]:
        """
        Returns current family members.

        Returns:
            List[Mapping[str, Any]]: List of family members.
        """
        if self._user_family is None:
            self._user_family = self.get_family_home()
        return self._user_family["members"]

    @property
    def enough_space(self) -> bool:
        """
        Checks if there is space left in the family (max 6 members).

        Returns:
            bool: True if space available, False otherwise.
        """
        return len(self.members) < 6
