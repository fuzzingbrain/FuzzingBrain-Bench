# Bug catalog (69)

The 69 end-to-end gradeable bugs. Browse the same data from the CLI:

```bash
./fb-bench list                 # 69 bugs + K_b
./fb-bench show <bug_id>         # full description + upstream link
```

`K_b` columns — the flags **required for PASS** on each bug:
**R**each · **C**rash · **Cl**ass · **S**ite (✅ = required, · = N/A).

| # | bug_id | project | lang | bug class | R | C | Cl | S |
|--:|---|---|:--:|---|:--:|:--:|:--:|:--:|
| 1 | [`avro-decompression-bomb`](https://github.com/apache/avro/pull/3625) | avro | Java | oom | · | ✅ | ✅ | · |
| 2 | [`avro-neg-block-size`](https://github.com/apache/avro/pull/3623) | avro | C | allocation-size-too-big | ✅ | ✅ | ✅ | ✅ |
| 3 | [`avro-neg-string-len`](https://github.com/apache/avro/pull/3622) | avro | C | — | ✅ | ✅ | · | ✅ |
| 4 | [`binutils-rust-demangle-oom`](https://sourceware.org/bugzilla/show_bug.cgi?id=33878) | binutils | C | oom | · | ✅ | ✅ | · |
| 5 | [`cups-utf8-charset-overflow`](https://github.com/OpenPrinting/cups/issues/1438) | cups | C | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 6 | [`dtc-fdt32-misalign`](https://github.com/dgibson/dtc/issues/178) | dtc | C | misaligned-access | ✅ | ✅ | ✅ | ✅ |
| 7 | [`flatbuffers-flexbuffers-tostring-overflow`](https://github.com/google/flatbuffers/issues/9008) | flatbuffers | C++ | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 8 | [`flatbuffers-parser-deserialize-uaf`](https://github.com/google/flatbuffers/issues/9009) | flatbuffers | C++ | use-after-free | · | ✅ | · | · |
| 9 | [`flatbuffers-reflection-verifier-overflow`](https://github.com/google/flatbuffers/issues/9040) | flatbuffers | C++ | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 10 | [`freerdp-ntlm-memleak`](https://github.com/FreeRDP/FreeRDP/issues/12603) | FreeRDP | C | memory-leak | ✅ | · | ✅ | ✅ |
| 11 | [`freetype-ftbitmapcopy-uaf`](https://gitlab.freedesktop.org/freetype/freetype/-/issues/1385) | freetype | C | heap-use-after-free | ✅ | ✅ | ✅ | ✅ |
| 12 | [`fwupd-cab-mszip-bomb`](https://github.com/fwupd/fwupd/issues/9790) | fwupd | C | oom | · | ✅ | ✅ | · |
| 13 | [`fwupd-logitech-oob-read`](https://github.com/fwupd/fwupd/issues/9792) | fwupd | C | heap-buffer-overflow | · | ✅ | ✅ | ✅ |
| 14 | [`fwupd-logitech-stack-overflow`](https://github.com/fwupd/fwupd/issues/9779) | fwupd | C | stack-overflow | · | ✅ | ✅ | · |
| 15 | [`fwupd-sbatlevel-underflow`](https://github.com/fwupd/fwupd/issues/9659) | fwupd | C | oom | · | ✅ | ✅ | · |
| 16 | [`ghidra-cplus-demangle-oom`](https://github.com/NationalSecurityAgency/ghidra/security/advisories/GHSA-m94m-fqr3-x442) | Ghidra | C | oom | · | ✅ | ✅ | · |
| 17 | [`ghidra-rust-demangle-oom`](https://github.com/NationalSecurityAgency/ghidra/security/advisories/GHSA-m94m-fqr3-x442) | Ghidra | C | oom | ✅ | ✅ | ✅ | ✅ |
| 18 | [`graal-regexlexer-oob`](https://github.com/oracle/graaljs/issues/986) | graal | Java | uncaught-exception | · | ✅ | ✅ | · |
| 19 | [`graaljs-illformed-locale`](https://github.com/oracle/graaljs/issues/985) | graaljs | Java | uncaught-exception | · | ✅ | ✅ | · |
| 20 | [`harfbuzz-fontations-oob-write`](https://github.com/harfbuzz/harfbuzz/issues/5946) | harfbuzz | C++ | stack-buffer-overflow | · | ✅ | ✅ | ✅ |
| 21 | [`hunspell-hashmgr-tablesize-oom`](https://github.com/hunspell/hunspell/issues/1116) | hunspell | C++ | oom | · | ✅ | ✅ | · |
| 22 | [`icu-translit-rule-dtor-uaf`](https://unicode-org.atlassian.net/browse/ICU-23365) | icu | C++ | segv | ✅ | ✅ | ✅ | ✅ |
| 23 | [`icu-translit-rule-uaf`](https://unicode-org.atlassian.net/browse/ICU-23365) | icu | C++ | memory-leak | ✅ | · | ✅ | ✅ |
| 24 | [`imagemagick-kernelinfo-alloc`](https://github.com/ImageMagick/ImageMagick/security/advisories/GHSA-q62c-h75r-2xhc) | imagemagick | C | — | ✅ | ✅ | · | ✅ |
| 25 | [`imagemagick-msl-comment-npd`](https://github.com/ImageMagick/ImageMagick/security/advisories/GHSA-5vx3-wx4q-6cj8) | ImageMagick | C++ | abort | ✅ | ✅ | · | ✅ |
| 26 | [`imagemagick-msl-stack-overflow`](https://github.com/ImageMagick/ImageMagick/security/advisories/GHSA-9vj4-wc7r-p844) | ImageMagick | C | stack-overflow | · | ✅ | ✅ | · |
| 27 | [`jq-dump-op-npd`](https://github.com/jqlang/jq/issues/3458) | jq | C | segv | ✅ | ✅ | ✅ | ✅ |
| 28 | [`jsonjava-jsonml-classcast`](https://github.com/stleary/JSON-java/issues/1034) | json-java | Java | class-cast | ✅ | ✅ | ✅ | ✅ |
| 29 | [`jsonjava-unescape-numformat`](https://github.com/stleary/JSON-java/issues/1036) | json-java | Java | uncaught-exception | ✅ | ✅ | ✅ | ✅ |
| 30 | [`jsonjava-unescape-strindex`](https://github.com/stleary/JSON-java/issues/1035) | json-java | Java | oob-read | ✅ | ✅ | ✅ | ✅ |
| 31 | [`libaom-av1-config-assert`](https://aomedia.googlesource.com/aom/) | libaom | C++ | — | ✅ | ✅ | · | ✅ |
| 32 | [`libaom-restore-layer-overflow`](https://issues.chromium.org/issues/501657371) | libaom | C++ | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 33 | [`libaom-svc-encoder-hang`](https://issues.chromium.org/issues/505976409) | libaom | C++ | oom | · | ✅ | · | · |
| 34 | [`libavif-jni-signext`](https://github.com/AOMediaCodec/libavif/issues/3177) | libavif | C++ | heap-buffer-overflow | · | ✅ | ✅ | ✅ |
| 35 | [`libheif-image-crop-overflow`](https://github.com/strukturag/libheif/issues/1746) | libheif | C++ | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 36 | [`libpng-zlib-inflate-uaf`](https://github.com/pnggroup/libpng/security/advisories/GHSA-qvg3-h654-xq3j) | libpng | C | heap-use-after-free | ✅ | ✅ | ✅ | ✅ |
| 37 | [`libvpx-vp9-encoder-caq-assert`](https://issues.webmproject.org/issues/497896136) | libvpx | C | abrt | ✅ | ✅ | · | ✅ |
| 38 | [`libvpx-vp9-reconfig-overflow`](https://issues.webmproject.org/issues/501696590) | libvpx | C++ | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 39 | [`libvpx-vp9-svc-ratectrl-ub`](https://issues.webmproject.org/issues/508317885) | libvpx | C++ | undefined-behavior | ✅ | ✅ | · | · |
| 40 | [`libvpx-vpx-img-flip-ub`](https://issues.webmproject.org/issues/512911654) | libvpx | C++ | undefined-behavior | ✅ | ✅ | · | · |
| 41 | [`libwebp-muxassemble-npd`](https://issues.webmproject.org/issues/497882857) | libwebp | C | segv | ✅ | ✅ | ✅ | ✅ |
| 42 | [`libwebp-sharpyuv-convert-stride-oob`](https://issues.webmproject.org/issues/501147575) | libwebp | C++ | segv | ✅ | ✅ | ✅ | ✅ |
| 43 | [`libwebp-sharpyuv-gamma-oob`](https://github.com/webmproject/libwebp/security/advisories/GHSA-6gpr-h4hq-vh57) | libwebp | C | segv | ✅ | ✅ | ✅ | ✅ |
| 44 | [`libwebsockets-lhp-class-oob`](https://github.com/warmcat/libwebsockets (private disclosure to andy@warmcat.com per SECURITY.md; fixed bd57edb5fc)) | libwebsockets | C | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 45 | [`mongoose-mg-match-overflow`](https://github.com/cesanta/mongoose/issues/3393) | mongoose | C | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 46 | [`mongoose-mqtt-nextprop-oob`](https://github.com/cesanta/mongoose/issues/3419) | mongoose | C | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 47 | [`ndpi-hex-decode-sscanf`](https://github.com/ntop/nDPI/issues/3159) | ndpi | C | segv | ✅ | ✅ | ✅ | ✅ |
| 48 | [`netsnmp-smux-rreq-uaf`](https://github.com/net-snmp/net-snmp/issues/1098) | net-snmp | C | heap-use-after-free | ✅ | ✅ | ✅ | ✅ |
| 49 | [`netsnmp-vacm-parse-npd`](https://github.com/net-snmp/net-snmp/issues/1052) | net-snmp | C | segv | ✅ | ✅ | ✅ | ✅ |
| 50 | [`opcua-pubsub-json-assert`](https://github.com/open62541/open62541/pull/7680) | open62541 | C | — | ✅ | ✅ | · | ✅ |
| 51 | [`opencv-yaml-parsekey`](https://github.com/opencv/opencv/issues/28619) | opencv | C++ | heap-buffer-overflow | · | ✅ | ✅ | ✅ |
| 52 | [`openh264-scenechange-overflow`](https://github.com/cisco/openh264/issues/3926) | openh264 | C++ | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 53 | [`openldap-ldif-stack-underflow`](https://bugs.openldap.org/show_bug.cgi?id=10431) | openldap | C | stack-buffer-underflow | ✅ | ✅ | ✅ | ✅ |
| 54 | [`openldap-parse-whsp`](https://bugs.openldap.org/show_bug.cgi?id=10430) | openldap | C | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 55 | [`openscreen-jsoncpp-error-message-overflow`](https://github.com/open-source-parsers/jsoncpp/issues/1682) | openscreen | C++ | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 56 | [`openscreen-jsoncpp-nonobject-oob`](https://issues.chromium.org/issues/505902443) | openscreen | C++ | abrt | · | ✅ | · | · |
| 57 | [`openssl-des-ofb-cfb-overread`](https://github.com/openssl/openssl/issues/30284) | openssl | C | stack-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 58 | [`ots-processgeneric-npd`](https://github.com/khaledhosny/ots/issues/308) | ots | C++ | segv | ✅ | ✅ | ✅ | ✅ |
| 59 | [`pdfbox-cmap-bfrange-aioob`](https://github.com/apache/pdfbox/pull/411) | pdfbox | Java | oob-read | ✅ | ✅ | ✅ | ✅ |
| 60 | [`pdfbox-inlineimage-type-confusion`](https://github.com/apache/pdfbox/pull/410) | pdfbox | Java | class-cast | ✅ | ✅ | ✅ | ✅ |
| 61 | [`pdfbox-pfb-negative-array`](https://github.com/apache/pdfbox/pull/412) | pdfbox | Java | uncaught-exception | ✅ | ✅ | ✅ | ✅ |
| 62 | [`simdutf-utf16-utf8-overflow`](https://github.com/simdutf/simdutf/issues/911) | simdutf | C++ | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 63 | [`skia-raster8888-blur-oob`](https://issues.chromium.org/issues/508075339) | skia | C++ | out-of-bounds-access | · | ✅ | · | · |
| 64 | [`spirv-orderblocks-segv`](https://github.com/KhronosGroup/SPIRV-Tools/issues/6663) | spirv-tools | C++ | segv | ✅ | ✅ | ✅ | ✅ |
| 65 | [`spirv-tools-friendlynamemapper-overflow`](https://github.com/KhronosGroup/SPIRV-Tools/issues/6664) | spirv-tools | C++ | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
| 66 | [`systemd-hwdb-trie-oob-read`](https://github.com/systemd/systemd/pull/42347) | systemd | C | segv | ✅ | ✅ | ✅ | ✅ |
| 67 | [`systemd-pe-binary-dos`](https://github.com/systemd/systemd/pull/42348) | systemd | C | timeout | · | ✅ | ✅ | · |
| 68 | [`upx-elf32-pack2-memleak`](https://github.com/upx/upx/issues/945) | upx | C++ | memory-leak | ✅ | · | ✅ | ✅ |
| 69 | [`upx-elf64-generate-overflow`](https://github.com/upx/upx/issues/947) | upx | C++ | heap-buffer-overflow | ✅ | ✅ | ✅ | ✅ |
