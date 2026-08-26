import pytest

from tools.linkedin_api import (
    build_authorize_url,
    build_post_payload,
    parse_callback,
    post_url_from_id,
    token_is_valid,
)


class TestBuildAuthorizeUrl:
    def test_points_at_the_linkedin_authorization_endpoint(self):
        url = build_authorize_url("id123", "http://localhost:50001/callback", "st4te")
        assert url.startswith("https://www.linkedin.com/oauth/v2/authorization?")

    def test_carries_client_id_state_and_encoded_redirect(self):
        url = build_authorize_url("id123", "http://localhost:50001/callback", "st4te")
        assert "client_id=id123" in url
        assert "state=st4te" in url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A50001%2Fcallback" in url

    def test_requests_exactly_the_four_granted_scopes(self):
        url = build_authorize_url("id123", "http://localhost:50001/callback", "st4te")
        assert "scope=openid+profile+email+w_member_social" in url


class TestParseCallback:
    def test_extracts_the_code(self):
        assert parse_callback("/callback?code=abc&state=st4te", "st4te") == "abc"

    def test_rejects_a_state_mismatch(self):
        with pytest.raises(ValueError, match="state"):
            parse_callback("/callback?code=abc&state=forged", "st4te")

    def test_rejects_a_denied_authorization(self):
        with pytest.raises(ValueError, match="user_cancelled_login"):
            parse_callback(
                "/callback?error=user_cancelled_login&error_description=x&state=st4te",
                "st4te",
            )

    def test_rejects_a_callback_without_code(self):
        with pytest.raises(ValueError, match="code"):
            parse_callback("/callback?state=st4te", "st4te")


class TestTokenIsValid:
    def test_accepts_a_token_that_expires_in_the_future(self):
        assert token_is_valid({"access_token": "t", "expires_at": 2000.0}, now=1000.0)

    def test_rejects_an_expired_token(self):
        assert not token_is_valid({"access_token": "t", "expires_at": 500.0}, now=1000.0)

    def test_rejects_a_token_inside_the_expiry_margin(self):
        # 60s margin: a token about to expire must not be used mid-flow.
        assert not token_is_valid({"access_token": "t", "expires_at": 1030.0}, now=1000.0)

    def test_rejects_a_missing_or_malformed_token(self):
        assert not token_is_valid(None, now=1000.0)
        assert not token_is_valid({}, now=1000.0)
        assert not token_is_valid({"expires_at": 2000.0}, now=1000.0)


class TestBuildPostPayload:
    def test_builds_the_ugc_post_shape_linkedin_expects(self):
        payload = build_post_payload("urn:li:person:a1b2", "texto do post")
        assert payload == {
            "author": "urn:li:person:a1b2",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": "texto do post"},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

    def test_rejects_empty_text(self):
        with pytest.raises(ValueError, match="empty"):
            build_post_payload("urn:li:person:a1b2", "   ")

    def test_rejects_text_over_the_linkedin_limit(self):
        with pytest.raises(ValueError, match="3000"):
            build_post_payload("urn:li:person:a1b2", "x" * 3001)


class TestPostUrlFromId:
    def test_wraps_the_returned_urn_in_the_feed_update_url(self):
        assert (
            post_url_from_id("urn:li:share:7654321")
            == "https://www.linkedin.com/feed/update/urn:li:share:7654321/"
        )

    def test_rejects_a_blank_id(self):
        with pytest.raises(ValueError, match="id"):
            post_url_from_id("")


from tools.linkedin_api import build_register_upload_payload, parse_register_upload


class TestImagePayloads:
    def test_post_with_asset_switches_to_image_and_carries_media(self):
        payload = build_post_payload(
            "urn:li:person:a1b2", "texto do post",
            asset_urn="urn:li:digitalmediaAsset:xyz", alt_text="diagrama",
        )
        share = payload["specificContent"]["com.linkedin.ugc.ShareContent"]
        assert share["shareMediaCategory"] == "IMAGE"
        assert share["media"] == [
            {
                "status": "READY",
                "media": "urn:li:digitalmediaAsset:xyz",
                "description": {"text": "diagrama"},
            }
        ]

    def test_post_without_asset_stays_text_only(self):
        share = build_post_payload("urn:li:person:a1b2", "texto do post")[
            "specificContent"
        ]["com.linkedin.ugc.ShareContent"]
        assert share["shareMediaCategory"] == "NONE"
        assert "media" not in share

    def test_register_upload_asks_for_the_feedshare_recipe_as_owner(self):
        payload = build_register_upload_payload("urn:li:person:a1b2")
        request = payload["registerUploadRequest"]
        assert request["recipes"] == ["urn:li:digitalmediaRecipe:feedshare-image"]
        assert request["owner"] == "urn:li:person:a1b2"

    def test_parse_register_upload_extracts_asset_and_url(self):
        body = {
            "value": {
                "asset": "urn:li:digitalmediaAsset:xyz",
                "uploadMechanism": {
                    "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest": {
                        "uploadUrl": "https://upload.example/u"
                    }
                },
            }
        }
        assert parse_register_upload(body) == (
            "urn:li:digitalmediaAsset:xyz",
            "https://upload.example/u",
        )

    def test_parse_register_upload_rejects_odd_shapes(self):
        import pytest as _pytest
        with _pytest.raises(ValueError, match="registerUpload"):
            parse_register_upload({"value": {}})
