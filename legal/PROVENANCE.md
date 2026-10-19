# Ownership and distribution review

## Current decision, 2026-10-19

The owner requested free open-source distribution again. Newly authored private
foundation files are now offered under GPL v3, alongside the inherited GPL v3
application. The scoped file list and authorship evidence are recorded in
open-source-transition.json. This does not grant rights in any third-party code.
The repeated comparison found no exact large-function matches with the restricted
original; matching fonts have independent OFL terms. Automated comparison cannot
prove the absence of partial copies. Third-party notices and corresponding-source
responsibilities still apply. Historical commercial drafts are not shipped.

The previous commercial review below is retained as history, not current licensing.

This candidate starts from public GPL release 0.5.1, commit
887b7a3c57a83166277189e1809536dfda4373dd. Its Git history records one author identity,
BochkaPiva. The current owner requested a commercial successor. That history is
evidence to review, not proof of rights in every contribution or resource.

Original application code was independently implemented during this task; see
THIRD_PARTY.md. Earlier prototype code was carried into the public application.
No assertion of permission to redistribute Faygooich/Glassy-Music-Widget is made.
Its code, icons and translations must not be introduced into this successor.

Inherited GPL headers are deliberately retained until the owner completes the
rights/relicensing review. New commercial-foundation files carry a separate
LicenseRef. LICENSE identifies this as a private development candidate, not a
completed relicensing of all inherited material. Do not publish it as proprietary
software while code_rights is false. Old public GPL grants remain unchanged.

Before public distribution, record ownership of the initial implementation and
carried-over prototype modules, any external contributions, fonts and graphics;
resolve incompatible code by replacement or permission. Then approve exact file
relicensing and customer terms. A blanket text replacement is not this review.

Runtime modules used: QtCore, QtGui, QtWidgets, QtNetwork. QtTest is test-only and
excluded from the packaged application. WebEngine, Charts, DataVisualization and
PDF must not be bundled. PySide6 Essentials and shiboken6 use the LGPL option;
audit the exact shipped Qt plugins and third-party notices as part of release.

The build keeps Qt DLLs external and does not hash-pin them at runtime. Test
replacement with a compatible Qt build and provide the required corresponding
sources for the exact versions on the release distribution infrastructure.
Vendor URLs alone are not a completed corresponding-source delivery process.
