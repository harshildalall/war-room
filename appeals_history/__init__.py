# appeal_history
#
# Operational database for de-identified appeal records.
# Runs as a separate MongoDB database (appeal_history) on the same cluster
# as the counterclaim evidence database — single client, two database handles.
#
# PHI policy: no member names, member IDs, DOB, address, treating physician
# names, or patient clinical narratives are written to this database.