#  Licensed to Elasticsearch B.V. under one or more contributor
#  license agreements. See the NOTICE file distributed with
#  this work for additional information regarding copyright
#  ownership. Elasticsearch B.V. licenses this file to you under
#  the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
# 	http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing,
#  software distributed under the License is distributed on an
#  "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#  KIND, either express or implied.  See the License for the
#  specific language governing permissions and limitations
#  under the License.

from copy import deepcopy

from pytest import raises, warns

from elasticsearch_dsl import AsyncSearch, Document, Q, query
from elasticsearch_dsl.exceptions import IllegalOperation


def test_expand__to_dot_is_respected():
    s = AsyncSearch().query("match", a__b=42, _expand__to_dot=False)

    assert {"query": {"match": {"a__b": 42}}} == s.to_dict()


async def test_execute_uses_cache():
    s = AsyncSearch()
    r = object()
    s._response = r

    assert r is await s.execute()


async def test_cache_can_be_ignored(async_mock_client):
    s = AsyncSearch(using="mock")
    r = object()
    s._response = r
    await s.execute(ignore_cache=True)

    async_mock_client.search.assert_awaited_once_with(index=None, body={})


async def test_iter_iterates_over_hits():
    s = AsyncSearch()
    s._response = [1, 2, 3]

    assert [1, 2, 3] == [hit async for hit in s]


def test_cache_isnt_cloned():
    s = AsyncSearch()
    s._response = object()

    assert not hasattr(s._clone(), "_response")


def test_search_starts_with_no_query():
    s = AsyncSearch()

    assert s.query._proxied is None


def test_search_query_combines_query():
    s = AsyncSearch()

    s2 = s.query("match", f=42)
    assert s2.query._proxied == query.Match(f=42)
    assert s.query._proxied is None

    s3 = s2.query("match", f=43)
    assert s2.query._proxied == query.Match(f=42)
    assert s3.query._proxied == query.Bool(must=[query.Match(f=42), query.Match(f=43)])


def test_query_can_be_assigned_to():
    s = AsyncSearch()

    q = Q("match", title="python")
    s.query = q

    assert s.query._proxied is q


def test_query_can_be_wrapped():
    s = AsyncSearch().query("match", title="python")

    s.query = Q("function_score", query=s.query, field_value_factor={"field": "rating"})

    assert {
        "query": {
            "function_score": {
                "functions": [{"field_value_factor": {"field": "rating"}}],
                "query": {"match": {"title": "python"}},
            }
        }
    } == s.to_dict()


def test_using():
    o = object()
    o2 = object()
    s = AsyncSearch(using=o)
    assert s._using is o
    s2 = s.using(o2)
    assert s._using is o
    assert s2._using is o2


def test_methods_are_proxied_to_the_query():
    s = AsyncSearch().query("match_all")

    assert s.query.to_dict() == {"match_all": {}}


def test_query_always_returns_search():
    s = AsyncSearch()

    assert isinstance(s.query("match", f=42), AsyncSearch)


def test_source_copied_on_clone():
    s = AsyncSearch().source(False)
    assert s._clone()._source == s._source
    assert s._clone()._source is False

    s2 = AsyncSearch().source([])
    assert s2._clone()._source == s2._source
    assert s2._source == []

    s3 = AsyncSearch().source(["some", "fields"])
    assert s3._clone()._source == s3._source
    assert s3._clone()._source == ["some", "fields"]


def test_copy_clones():
    from copy import copy

    s1 = AsyncSearch().source(["some", "fields"])
    s2 = copy(s1)

    assert s1 == s2
    assert s1 is not s2


def test_aggs_allow_two_metric():
    s = AsyncSearch()

    s.aggs.metric("a", "max", field="a").metric("b", "max", field="b")

    assert s.to_dict() == {
        "aggs": {"a": {"max": {"field": "a"}}, "b": {"max": {"field": "b"}}}
    }


def test_aggs_get_copied_on_change():
    s = AsyncSearch().query("match_all")
    s.aggs.bucket("per_tag", "terms", field="f").metric(
        "max_score", "max", field="score"
    )

    s2 = s.query("match_all")
    s2.aggs.bucket("per_month", "date_histogram", field="date", interval="month")
    s3 = s2.query("match_all")
    s3.aggs["per_month"].metric("max_score", "max", field="score")
    s4 = s3._clone()
    s4.aggs.metric("max_score", "max", field="score")

    d = {
        "query": {"match_all": {}},
        "aggs": {
            "per_tag": {
                "terms": {"field": "f"},
                "aggs": {"max_score": {"max": {"field": "score"}}},
            }
        },
    }

    assert d == s.to_dict()
    d["aggs"]["per_month"] = {"date_histogram": {"field": "date", "interval": "month"}}
    assert d == s2.to_dict()
    d["aggs"]["per_month"]["aggs"] = {"max_score": {"max": {"field": "score"}}}
    assert d == s3.to_dict()
    d["aggs"]["max_score"] = {"max": {"field": "score"}}
    assert d == s4.to_dict()


def test_search_index():
    s = AsyncSearch(index="i")
    assert s._index == ["i"]
    s = s.index("i2")
    assert s._index == ["i", "i2"]
    s = s.index("i3")
    assert s._index == ["i", "i2", "i3"]
    s = s.index()
    assert s._index is None
    s = AsyncSearch(index=("i", "i2"))
    assert s._index == ["i", "i2"]
    s = AsyncSearch(index=["i", "i2"])
    assert s._index == ["i", "i2"]
    s = AsyncSearch()
    s = s.index("i", "i2")
    assert s._index == ["i", "i2"]
    s2 = s.index("i3")
    assert s._index == ["i", "i2"]
    assert s2._index == ["i", "i2", "i3"]
    s = AsyncSearch()
    s = s.index(["i", "i2"], "i3")
    assert s._index == ["i", "i2", "i3"]
    s2 = s.index("i4")
    assert s._index == ["i", "i2", "i3"]
    assert s2._index == ["i", "i2", "i3", "i4"]
    s2 = s.index(["i4"])
    assert s2._index == ["i", "i2", "i3", "i4"]
    s2 = s.index(("i4", "i5"))
    assert s2._index == ["i", "i2", "i3", "i4", "i5"]


def test_doc_type_document_class():
    class MyDocument(Document):
        pass

    s = AsyncSearch(doc_type=MyDocument)
    assert s._doc_type == [MyDocument]
    assert s._doc_type_map == {}

    s = AsyncSearch().doc_type(MyDocument)
    assert s._doc_type == [MyDocument]
    assert s._doc_type_map == {}


def test_knn():
    s = AsyncSearch()

    with raises(TypeError):
        s.knn()
    with raises(TypeError):
        s.knn("field")
    with raises(TypeError):
        s.knn("field", 5)
    with raises(ValueError):
        s.knn("field", 5, 100)
    with raises(ValueError):
        s.knn("field", 5, 100, query_vector=[1, 2, 3], query_vector_builder={})

    s = s.knn("field", 5, 100, query_vector=[1, 2, 3])
    assert {
        "knn": {
            "field": "field",
            "k": 5,
            "num_candidates": 100,
            "query_vector": [1, 2, 3],
        }
    } == s.to_dict()

    s = s.knn(
        k=4,
        num_candidates=40,
        boost=0.8,
        field="name",
        query_vector_builder={
            "text_embedding": {"model_id": "foo", "model_text": "search text"}
        },
    )
    assert {
        "knn": [
            {
                "field": "field",
                "k": 5,
                "num_candidates": 100,
                "query_vector": [1, 2, 3],
            },
            {
                "field": "name",
                "k": 4,
                "num_candidates": 40,
                "query_vector_builder": {
                    "text_embedding": {"model_id": "foo", "model_text": "search text"}
                },
                "boost": 0.8,
            },
        ]
    } == s.to_dict()


def test_rank():
    s = AsyncSearch()
    s.rank(rrf=False)
    assert {} == s.to_dict()

    s = s.rank(rrf=True)
    assert {"rank": {"rrf": {}}} == s.to_dict()

    s = s.rank(rrf={"window_size": 50, "rank_constant": 20})
    assert {"rank": {"rrf": {"window_size": 50, "rank_constant": 20}}} == s.to_dict()


def test_sort():
    s = AsyncSearch()
    s = s.sort("fielda", "-fieldb")

    assert ["fielda", {"fieldb": {"order": "desc"}}] == s._sort
    assert {"sort": ["fielda", {"fieldb": {"order": "desc"}}]} == s.to_dict()

    s = s.sort()
    assert [] == s._sort
    assert AsyncSearch().to_dict() == s.to_dict()


def test_sort_by_score():
    s = AsyncSearch()
    s = s.sort("_score")
    assert {"sort": ["_score"]} == s.to_dict()

    s = AsyncSearch()
    with raises(IllegalOperation):
        s.sort("-_score")


def test_collapse():
    s = AsyncSearch()

    inner_hits = {"name": "most_recent", "size": 5, "sort": [{"@timestamp": "desc"}]}
    s = s.collapse("user.id", inner_hits=inner_hits, max_concurrent_group_searches=4)

    assert {
        "field": "user.id",
        "inner_hits": {
            "name": "most_recent",
            "size": 5,
            "sort": [{"@timestamp": "desc"}],
        },
        "max_concurrent_group_searches": 4,
    } == s._collapse
    assert {
        "collapse": {
            "field": "user.id",
            "inner_hits": {
                "name": "most_recent",
                "size": 5,
                "sort": [{"@timestamp": "desc"}],
            },
            "max_concurrent_group_searches": 4,
        }
    } == s.to_dict()

    s = s.collapse()
    assert {} == s._collapse
    assert AsyncSearch().to_dict() == s.to_dict()


def test_slice():
    s = AsyncSearch()
    assert {"from": 3, "size": 7} == s[3:10].to_dict()
    assert {"from": 0, "size": 5} == s[:5].to_dict()
    assert {"from": 3, "size": 10} == s[3:].to_dict()
    assert {"from": 0, "size": 0} == s[0:0].to_dict()
    assert {"from": 20, "size": 0} == s[20:0].to_dict()


def test_slice_twice():
    with warns(DeprecationWarning, match="Slicing multiple times .*"):
        s = AsyncSearch()
        s[10:20][2:]


def test_index():
    s = AsyncSearch()
    assert {"from": 3, "size": 1} == s[3].to_dict()


def test_search_to_dict():
    s = AsyncSearch()
    assert {} == s.to_dict()

    s = s.query("match", f=42)
    assert {"query": {"match": {"f": 42}}} == s.to_dict()

    assert {"query": {"match": {"f": 42}}, "size": 10} == s.to_dict(size=10)

    s.aggs.bucket("per_tag", "terms", field="f").metric(
        "max_score", "max", field="score"
    )
    d = {
        "aggs": {
            "per_tag": {
                "terms": {"field": "f"},
                "aggs": {"max_score": {"max": {"field": "score"}}},
            }
        },
        "query": {"match": {"f": 42}},
    }
    assert d == s.to_dict()

    s = AsyncSearch(extra={"size": 5})
    assert {"size": 5} == s.to_dict()
    s = s.extra(from_=42)
    assert {"size": 5, "from": 42} == s.to_dict()


def test_complex_example():
    s = AsyncSearch()
    s = (
        s.query("match", title="python")
        .query(~Q("match", title="ruby"))
        .filter(Q("term", category="meetup") | Q("term", category="conference"))
        .collapse("user_id")
        .post_filter("terms", tags=["prague", "czech"])
        .script_fields(more_attendees="doc['attendees'].value + 42")
    )

    s.aggs.bucket("per_country", "terms", field="country").metric(
        "avg_attendees", "avg", field="attendees"
    )

    s.query.minimum_should_match = 2

    s = s.highlight_options(order="score").highlight("title", "body", fragment_size=50)

    assert {
        "query": {
            "bool": {
                "filter": [
                    {
                        "bool": {
                            "should": [
                                {"term": {"category": "meetup"}},
                                {"term": {"category": "conference"}},
                            ]
                        }
                    }
                ],
                "must": [{"match": {"title": "python"}}],
                "must_not": [{"match": {"title": "ruby"}}],
                "minimum_should_match": 2,
            }
        },
        "post_filter": {"terms": {"tags": ["prague", "czech"]}},
        "aggs": {
            "per_country": {
                "terms": {"field": "country"},
                "aggs": {"avg_attendees": {"avg": {"field": "attendees"}}},
            }
        },
        "collapse": {"field": "user_id"},
        "highlight": {
            "order": "score",
            "fields": {"title": {"fragment_size": 50}, "body": {"fragment_size": 50}},
        },
        "script_fields": {"more_attendees": {"script": "doc['attendees'].value + 42"}},
    } == s.to_dict()


def test_reverse():
    d = {
        "query": {
            "filtered": {
                "filter": {
                    "bool": {
                        "should": [
                            {"term": {"category": "meetup"}},
                            {"term": {"category": "conference"}},
                        ]
                    }
                },
                "query": {
                    "bool": {
                        "must": [{"match": {"title": "python"}}],
                        "must_not": [{"match": {"title": "ruby"}}],
                        "minimum_should_match": 2,
                    }
                },
            }
        },
        "post_filter": {"bool": {"must": [{"terms": {"tags": ["prague", "czech"]}}]}},
        "aggs": {
            "per_country": {
                "terms": {"field": "country"},
                "aggs": {"avg_attendees": {"avg": {"field": "attendees"}}},
            }
        },
        "sort": ["title", {"category": {"order": "desc"}}, "_score"],
        "size": 5,
        "highlight": {"order": "score", "fields": {"title": {"fragment_size": 50}}},
        "suggest": {
            "my-title-suggestions-1": {
                "text": "devloping distibutd saerch engies",
                "term": {"size": 3, "field": "title"},
            }
        },
        "script_fields": {"more_attendees": {"script": "doc['attendees'].value + 42"}},
    }

    d2 = deepcopy(d)

    s = AsyncSearch.from_dict(d)

    # make sure we haven't modified anything in place
    assert d == d2
    assert {"size": 5} == s._extra
    assert d == s.to_dict()


def test_from_dict_doesnt_need_query():
    s = AsyncSearch.from_dict({"size": 5})

    assert {"size": 5} == s.to_dict()


async def test_params_being_passed_to_search(async_mock_client):
    s = AsyncSearch(using="mock")
    s = s.params(routing="42")
    await s.execute()

    async_mock_client.search.assert_awaited_once_with(index=None, body={}, routing="42")


def test_source():
    assert {} == AsyncSearch().source().to_dict()

    assert {
        "_source": {"includes": ["foo.bar.*"], "excludes": ["foo.one"]}
    } == AsyncSearch().source(includes=["foo.bar.*"], excludes=["foo.one"]).to_dict()

    assert {"_source": False} == AsyncSearch().source(False).to_dict()

    assert {"_source": ["f1", "f2"]} == AsyncSearch().source(
        includes=["foo.bar.*"], excludes=["foo.one"]
    ).source(["f1", "f2"]).to_dict()


def test_source_on_clone():
    assert {
        "_source": {"includes": ["foo.bar.*"], "excludes": ["foo.one"]},
        "query": {"bool": {"filter": [{"term": {"title": "python"}}]}},
    } == AsyncSearch().source(includes=["foo.bar.*"]).source(
        excludes=["foo.one"]
    ).filter(
        "term", title="python"
    ).to_dict()
    assert {
        "_source": False,
        "query": {"bool": {"filter": [{"term": {"title": "python"}}]}},
    } == AsyncSearch().source(False).filter("term", title="python").to_dict()


def test_source_on_clear():
    assert (
        {}
        == AsyncSearch()
        .source(includes=["foo.bar.*"])
        .source(includes=None, excludes=None)
        .to_dict()
    )


def test_suggest_accepts_global_text():
    s = AsyncSearch.from_dict(
        {
            "suggest": {
                "text": "the amsterdma meetpu",
                "my-suggest-1": {"term": {"field": "title"}},
                "my-suggest-2": {"text": "other", "term": {"field": "body"}},
            }
        }
    )

    assert {
        "suggest": {
            "my-suggest-1": {
                "term": {"field": "title"},
                "text": "the amsterdma meetpu",
            },
            "my-suggest-2": {"term": {"field": "body"}, "text": "other"},
        }
    } == s.to_dict()


def test_suggest():
    s = AsyncSearch()
    s = s.suggest("my_suggestion", "pyhton", term={"field": "title"})

    assert {
        "suggest": {"my_suggestion": {"term": {"field": "title"}, "text": "pyhton"}}
    } == s.to_dict()


def test_exclude():
    s = AsyncSearch()
    s = s.exclude("match", title="python")

    assert {
        "query": {
            "bool": {
                "filter": [{"bool": {"must_not": [{"match": {"title": "python"}}]}}]
            }
        }
    } == s.to_dict()


async def test_delete_by_query(async_mock_client):
    s = AsyncSearch(using="mock").query("match", lang="java")
    await s.delete()

    async_mock_client.delete_by_query.assert_awaited_once_with(
        index=None, body={"query": {"match": {"lang": "java"}}}
    )


def test_update_from_dict():
    s = AsyncSearch()
    s.update_from_dict({"indices_boost": [{"important-documents": 2}]})
    s.update_from_dict({"_source": ["id", "name"]})
    s.update_from_dict({"collapse": {"field": "user_id"}})

    assert {
        "indices_boost": [{"important-documents": 2}],
        "_source": ["id", "name"],
        "collapse": {"field": "user_id"},
    } == s.to_dict()


def test_rescore_query_to_dict():
    s = AsyncSearch(index="index-name")

    positive_query = Q(
        "function_score",
        query=Q("term", tags="a"),
        script_score={"script": "_score * 1"},
    )

    negative_query = Q(
        "function_score",
        query=Q("term", tags="b"),
        script_score={"script": "_score * -100"},
    )

    s = s.query(positive_query)
    s = s.extra(
        rescore={"window_size": 100, "query": {"rescore_query": negative_query}}
    )
    assert s.to_dict() == {
        "query": {
            "function_score": {
                "query": {"term": {"tags": "a"}},
                "functions": [{"script_score": {"script": "_score * 1"}}],
            }
        },
        "rescore": {
            "window_size": 100,
            "query": {
                "rescore_query": {
                    "function_score": {
                        "query": {"term": {"tags": "b"}},
                        "functions": [{"script_score": {"script": "_score * -100"}}],
                    }
                }
            },
        },
    }

    assert s.to_dict(
        rescore={"window_size": 10, "query": {"rescore_query": positive_query}}
    ) == {
        "query": {
            "function_score": {
                "query": {"term": {"tags": "a"}},
                "functions": [{"script_score": {"script": "_score * 1"}}],
            }
        },
        "rescore": {
            "window_size": 10,
            "query": {
                "rescore_query": {
                    "function_score": {
                        "query": {"term": {"tags": "a"}},
                        "functions": [{"script_score": {"script": "_score * 1"}}],
                    }
                }
            },
        },
    }
