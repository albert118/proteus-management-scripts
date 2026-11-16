"""Exports a list of pre-defined matchers. Each parses the provided data and applies its rules to resolve if the content is (not) matched."""

from file_helper.validation.movie_content_matcher import MovieContentMatcher
from file_helper.validation.junk_matcher import JunkMatcher


def matches_movie_conent(data):
    return (
        MovieContentMatcher(data)
        .is_typed()
        .is_non_empty()
        .is_movie_or_related_content()
        .is_valid()
    )


def matches_media_junk(data, **kwargs):
    return (
        JunkMatcher(data)
        .is_typed()
        .is_non_empty()
        .is_garbage_type()
        .is_known_garbage()
        .is_known_garbage_media()
        .is_custom_cover_photo(**kwargs)
        .is_valid()
    )


def matches_provided_junk(data, **kwargs):
    return (
        JunkMatcher(data)
        .is_typed()
        .is_non_empty()
        .is_given_garabage_type(**kwargs)
        .is_valid()
    )
