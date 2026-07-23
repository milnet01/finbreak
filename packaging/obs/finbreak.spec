# finbreak.spec — OBS RPM recipe for openSUSE + Fedora (FIBR-0155).
#
# The payload is a PyInstaller --onedir frozen runtime under /usr/lib/finbreak/:
# it bundles its own Python + every pinned native (SQLCipher, qpdf, pdfium, Qt),
# so the security-critical stack is the exact pinned closure the gate tests, not
# a distro substitute (§ 3.2). Version comes from the tag via the _service
# set_version (never hand-typed, obs_packaging INV-6).
#
# NOTE (§ 5 — recall, confirm before the first OBS submit): the per-family
# package names below (Mesa-libGL1 vs mesa-libGL, libglib-2_0-0 vs glib2, …) and
# the %post/%postun scriptlet macro spellings are recalled distro facts; a wrong
# name hard-fails the OBS build, so they are checked against each target's real
# package index first.

Name:           finbreak
# Placeholder — the OBS set_version service (_service) writes the real version
# from the git tag. obs_packaging INV-6 asserts this is NOT a hard-coded semver.
Version:        0
Release:        0
Summary:        Private, offline desktop app for understanding your personal finances
License:        MIT
URL:            https://antsprojectshub.co.za/p/fin-break.html
Source0:        %{name}-%{version}.tar.gz
# Vendored wheel closure (both cp312 + cp313 ABIs + PyInstaller + its closure),
# built offline by the _service (§ 3.6). Unpacked to vendor/ in %prep.
Source1:        vendor.tar.gz
BuildRequires:  binutils
# Present at build time so the post-build filelist check sees the shared
# /usr/share/icons/hicolor/* dirs as owned (the Requires below doesn't get
# pulled into that isolated check) (FIBR-0155 §5).
BuildRequires:  hicolor-icon-theme

# Build-time python: the target's default python3 — EXCEPT openSUSE Leap (SLE),
# whose default python3 is the legacy 3.6. There, use the python313 module stack,
# which matches the cp313 vendored wheels (§ 3.6).
%if 0%{?sle_version}
%global py3     python3.13
%global py3pkg  python313
%else
%global py3     python3
%global py3pkg  python3
%endif

# --- Build-time collect-set: the libs PyInstaller must SEE so it bundles them
#     INTO the payload (the wider set from _build-smoke-in-container.sh). openSUSE
#     Tumbleweed + Leap share the SUSE names; Fedora is its own set. The python3
#     toolchain floats via %%{py3pkg} (python3 everywhere, python313 on Leap).
%if 0%{?suse_version}
BuildRequires:  %{py3pkg}
BuildRequires:  %{py3pkg}-devel
BuildRequires:  %{py3pkg}-pip
BuildRequires:  Mesa-libGL1
BuildRequires:  Mesa-libEGL1
BuildRequires:  libglib-2_0-0
# openSUSE splits libgthread-2.0.so.0 (a Qt dep) into its own package, unlike
# Fedora's glib2 which bundles it. Without it here, PyInstaller can't see the
# lib at freeze time and the %check self-test fails to load Qt (FIBR-0155).
BuildRequires:  libgthread-2_0-0
# PySide6's PyInstaller hook runs a freeze-time _check_if_openssl_enabled()
# that imports QtNetwork, which pulls libgssapi_krb5.so.2 (krb5). Missing it
# aborts the %build freeze, not just %check. Fedora's base image carries it.
BuildRequires:  krb5
BuildRequires:  libdbus-1-3
BuildRequires:  libX11-6
BuildRequires:  libxkbcommon0
BuildRequires:  libfreetype6
BuildRequires:  fontconfig
BuildRequires:  libharfbuzz0
%endif
%if 0%{?fedora}
BuildRequires:  python3
BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  mesa-libGL
BuildRequires:  mesa-libEGL
BuildRequires:  glib2
BuildRequires:  dbus-libs
BuildRequires:  libX11
BuildRequires:  libxkbcommon
BuildRequires:  freetype
BuildRequires:  fontconfig
BuildRequires:  harfbuzz
%endif

# --- Runtime deps: ONLY the host-left libGL/libEGL pair (the clean-room proof,
#     build-smoke.sh:95-96). Everything else travels in-bundle, so a Requires on
#     it would be over-broad + risk a wrong per-distro name (§ 3.5). The bundled
#     .so's are dlopen'd — invisible to RPM's auto-scanner, which we also disable
#     below — so libGL/libEGL are required explicitly.
%if 0%{?suse_version}
Requires:       Mesa-libGL1
Requires:       Mesa-libEGL1
%endif
%if 0%{?fedora}
Requires:       mesa-libGL
Requires:       mesa-libEGL
%endif
# Owns the shared /usr/share/icons/hicolor/*/apps dirs our PNGs land in, so the
# openSUSE filelist check doesn't fail on "directories not owned by a package"
# (same package name on openSUSE + Fedora + Debian) (FIBR-0155 §5).
Requires:       hicolor-icon-theme

# The payload is a bundled foreign tree: no debuginfo to split, and RPM must not
# auto-generate deps/provides from its hundreds of bundled libraries.
%global debug_package %{nil}
%global __requires_exclude_from ^%{_prefix}/lib/finbreak/.*$
%global __provides_exclude_from ^%{_prefix}/lib/finbreak/.*$

%description
finbreak is a private, offline desktop app for understanding your money. Import
bank statements (CSV, OFX, PDF), categorise transactions, and see where your
money goes — everything stored locally in an encrypted vault (SQLCipher AES-256,
Argon2id key). No accounts, no cloud, no tracking.

%prep
%setup -q
# Vendored wheels → vendor/ (offline %build source).
tar -xf %{SOURCE1}

%build
# Build venv on the target's build python (%{py3}: python3 everywhere, python3.13
# on Leap). Install the pinned runtime deps + the freezer OFFLINE from the
# vendored wheels — every build-phase `pip install --no-index` (obs_packaging
# INV-7). Deps are read straight from pyproject (single source of truth).
%{py3} -m venv _bvenv
. _bvenv/bin/activate
python3 -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > _deps.txt
pip install --no-index --find-links vendor/ -r _deps.txt pyinstaller==6.21.0
# Freeze --onedir targeting __main__.py. Flags mirror scripts/_build-smoke-in-container.sh
# (the gated onefile freeze) — the SAME collect/hidden-import set; only the output
# mode differs (--onedir vs --onefile). Keep in lockstep with that script and with
# debian/rules (§ 3.5 — the flag list is duplicated across the two recipes by design).
pyinstaller --onedir --name finbreak \
    --paths src \
    --add-data "src/finbreak/ui/icons:finbreak/ui/icons" \
    --add-data "src/finbreak/data:finbreak/data" \
    --hidden-import sqlcipher3 \
    --hidden-import pikepdf \
    --hidden-import PySide6.QtWidgets \
    --collect-binaries pikepdf \
    --collect-binaries sqlcipher3 \
    --collect-all argon2 \
    --collect-all _argon2_cffi_bindings \
    --collect-all ofxparse \
    --collect-all bs4 \
    --collect-all lxml \
    --collect-all pdfplumber \
    --collect-all pdfminer \
    --collect-all pypdfium2 \
    --collect-all pypdfium2_raw \
    --collect-all PIL \
    --collect-all cryptography \
    --collect-all certifi \
    --distpath dist --workpath _pybuild --specpath . \
    src/finbreak/__main__.py

%install
# Lay the onedir tree out under /usr/lib/finbreak/ (the bootloader is
# dist/finbreak/finbreak).
mkdir -p %{buildroot}%{_prefix}/lib/finbreak
cp -a dist/finbreak/. %{buildroot}%{_prefix}/lib/finbreak/
# The /usr/bin launcher wrapper (§ 3.4).
install -Dm0755 packaging/obs/finbreak.sh %{buildroot}%{_bindir}/finbreak
# Desktop entry + AppStream metainfo (§ 3.3).
install -Dm0644 packaging/obs/io.github.milnet01.finbreak.desktop \
    %{buildroot}%{_datadir}/applications/io.github.milnet01.finbreak.desktop
install -Dm0644 packaging/obs/io.github.milnet01.finbreak.metainfo.xml \
    %{buildroot}%{_datadir}/metainfo/io.github.milnet01.finbreak.metainfo.xml
# Hicolor icons renamed to the app-ID (themed-icon name = Icon= in the .desktop).
for s in 16 24 32 48 64 128 256 512; do
    install -Dm0644 assets/icon/finbreak-${s}.png \
        %{buildroot}%{_datadir}/icons/hicolor/${s}x${s}/apps/io.github.milnet01.finbreak.png
done

%check
# Prove the frozen native stack (Qt + SQLCipher + qpdf) travelled — the FIBR-0003
# sentinel — against the STAGED buildroot freeze (the package isn't installed at
# %check time, so a bare `finbreak` on $PATH would not resolve). offscreen: OBS
# build roots are headless. This is the sole automated gate on the onedir path.
FINBREAK_SELFTEST_DEBUG=1 QT_QPA_PLATFORM=offscreen %{buildroot}%{_prefix}/lib/finbreak/finbreak --self-test

%post
# Fedora needs explicit scriptlets to refresh the icon cache + desktop database.
# openSUSE does it automatically via file triggers (gtk-update-icon-cache on
# /usr/share/icons; desktop-file-utils on /usr/share/applications), so this is
# Fedora-only: the Fedora macros are undefined on openSUSE and, left unbraced,
# bash reads them as job specs ("fg: no job control"), failing %post (§5).
%if 0%{?fedora}
%icon_theme_cache_post
%desktop_database_post
%endif

%postun
%if 0%{?fedora}
%icon_theme_cache_postun
%desktop_database_postun
%endif

%files
%license LICENSE
%doc README.md
%{_bindir}/finbreak
%dir %{_prefix}/lib/finbreak
%{_prefix}/lib/finbreak/*
%{_datadir}/applications/io.github.milnet01.finbreak.desktop
%{_datadir}/metainfo/io.github.milnet01.finbreak.metainfo.xml
%{_datadir}/icons/hicolor/*/apps/io.github.milnet01.finbreak.png

%changelog
# Managed by the CHANGELOG/metainfo sync, not hand-edited here.
