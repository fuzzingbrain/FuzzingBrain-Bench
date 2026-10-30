#include <libwebsockets.h>

#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

#include <vector>

static lws_stateful_ret_t
lhp_fuzz_cb(lhp_ctx_t *ctx, char reason)
{
	(void)ctx;
	(void)reason;
	return LWS_SRET_OK;
}

static char *
fuzz_strdup(const char *s)
{
	size_t n = strlen(s) + 1;
	char *p = (char *)malloc(n);

	if (p)
		memcpy(p, s, n);

	return p;
}

static uint8_t
ascii_lower(uint8_t c)
{
	if (c >= 'A' && c <= 'Z')
		return (uint8_t)(c + ('a' - 'A'));

	return c;
}

static int
match_ascii_ci(const std::vector<uint8_t>& b, size_t pos, const char *pat)
{
	for (size_t n = 0; pat[n]; n++) {
		if (pos + n >= b.size())
			return 0;
		if (ascii_lower(b[pos + n]) != (uint8_t)pat[n])
			return 0;
	}

	return 1;
}

/*
 * lws_lhp_parse() is an in-memory HTML parser, but some recognized HTML / CSS
 * constructs can ask the surrounding renderer to fetch image or stylesheet
 * assets.  This harness is for the parser itself, so neutralize the attribute
 * and CSS keywords that would cross that boundary while keeping the input
 * otherwise byte-for-byte fuzz controlled.
 */
static void
neutralize_external_fetch_keywords(std::vector<uint8_t>& b)
{
	static const char * const pats[] = {
		"src",
		"href",
		"url",
		"background"
	};

	for (size_t i = 0; i < b.size(); i++)
		for (size_t p = 0; p < sizeof(pats) / sizeof(pats[0]); p++)
			if (match_ascii_ci(b, i, pats[p])) {
				size_t n = strlen(pats[p]);
				b[i + n - 1] = (uint8_t)'x';
			}
}

extern "C" int
LLVMFuzzerInitialize(int *argc, char ***argv)
{
	(void)argc;
	(void)argv;
	lws_set_log_level(0, NULL);
	return 0;
}

extern "C" int
LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
	static const size_t max_input = 65536;
	const size_t parse_size = size > max_input ? max_input : size;
	lws_displaylist_t displaylist;
	lws_surface_info_t ic;
	lws_dl_rend_t drt;
	lws_stateful_ret_t r;
	lhp_ctx_t ctx;

	std::vector<uint8_t> input;
	if (parse_size)
		input.assign(data, data + parse_size);
	neutralize_external_fetch_keywords(input);

	memset(&displaylist, 0, sizeof(displaylist));
	lws_display_dl_init(&displaylist, NULL);

	memset(&ic, 0, sizeof(ic));
	ic.wh_px[LWS_LHPREF_WIDTH].whole = 600;
	ic.wh_px[LWS_LHPREF_WIDTH].frac = 0;
	ic.wh_px[LWS_LHPREF_HEIGHT].whole = 448;
	ic.wh_px[LWS_LHPREF_HEIGHT].frac = 0;
	ic.wh_mm[LWS_LHPREF_WIDTH].whole = 114;
	ic.wh_mm[LWS_LHPREF_WIDTH].frac = 5000000;
	ic.wh_mm[LWS_LHPREF_HEIGHT].whole = 82;
	ic.wh_mm[LWS_LHPREF_HEIGHT].frac = 5000000;

	memset(&drt, 0, sizeof(drt));
	drt.dl = &displaylist;
	drt.w = ic.wh_px[LWS_LHPREF_WIDTH].whole;
	drt.h = ic.wh_px[LWS_LHPREF_HEIGHT].whole;

	memset(&ctx, 0, sizeof(ctx));
	if (lws_lhp_construct(&ctx, lhp_fuzz_cb, &drt, &ic))
		return 0;

	ctx.base_url = fuzz_strdup("[redacted-url]");
	if (!ctx.base_url)
		goto cleanup;

	{
		const uint8_t *p = input.empty() ? (const uint8_t *)"" : input.data();
		size_t len = input.size();

		r = lws_lhp_parse(&ctx, &p, &len);

		if (r == LWS_SRET_WANT_INPUT || r == LWS_SRET_OK) {
			const uint8_t *empty = p;
			size_t zero = 0;

			ctx.flags |= LHP_FLAG_DOCUMENT_END;
			(void)lws_lhp_parse(&ctx, &empty, &zero);
		}
	}

cleanup:
	lws_lhp_destruct(&ctx);
	lws_display_list_destroy(NULL, &displaylist);

	return 0;
}
