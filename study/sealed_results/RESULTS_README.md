# Identical E2/P8 files for both teams - 2 October 2026

All four current agreement rows and the frozen files were rechecked first. All 12 E2 result files and the one P8 result file then matched their full original-manifest SHA-256 hashes before joint extraction. E2's archive digest begins e27c71de; its complete locally computed digest is recorded.

These are exact byte copies of the two seals' result files. Both original manifests remain unchanged. No result JSON was parsed, result report read as text, or result interpreted by the packaging process. The names E2_SEALED and P8_SEALED preserve the original manifest paths; these copies have now been jointly extracted.

The shipped E2 verify_seal.py passed for all result files; missing historical inputs are reported as absent. P8's result and the available frozen code/model hashes match. Complete historical-input verification with p8_run.py --verify has not been claimed because many original inputs are not shipped here. See VERIFICATION_RECORD.json for exact scope.

Greg should send this same ZIP to Adam/Claude, alongside Final_signed_freeze_2026-10-02.zip, before discussing results. Each side then categorises independently against pre-registration v1.2 and deviations v3.1. This package contains no categorisation or interpretation.
