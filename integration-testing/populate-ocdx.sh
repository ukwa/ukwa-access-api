#cdx-indexer webarchive/collections/test/archive/ > test.cdx
curl -X POST --data-binary @test.cdx http://localhost:19090/tc
