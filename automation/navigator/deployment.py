# automation/navigator/deployment.py - split from navigator.py
# process_deployment: logo + checkboxes + Process
import time
import re
from playwright.sync_api import Page


class DeploymentMixin:
    """process_deployment: logo + checkboxes + Process"""

    def process_deployment(self, page, options=[]):
        print(f"   🚀 Deploy: {options}")
        try:
            # Wait for any full-page loading overlay (e.g. vld-overlay after CSV import)
            # before attempting to click the navbar logo or any page element.
            self._wait_for_long_loading(page)

            already_home = False
            try:
                if page.locator("text=Process Blueprints").first.is_visible(
                    timeout=1000
                ):
                    already_home = True
                    print("      ✅ Already on Home page")
            except:
                pass

            if not already_home:
                # Dismiss any blocking SweetAlert2 popup before clicking the logo
                try:
                    page.evaluate("""
                        const btn = document.querySelector(
                            '.swal2-popup.swal2-show button.swal2-confirm'
                        );
                        if (btn && btn.offsetParent !== null) btn.click();
                    """)
                    time.sleep(0.4)
                except Exception:
                    pass

                print("      🏠 Navigating to Home page...")
                logo = page.locator(".brand-link, .logo, a.navbar-brand").first
                if not logo.is_visible():
                    logo = page.locator("a").filter(has_text="The Brick").first
                if not logo.is_visible():
                    logo = page.locator(
                        "nav a:first-child, .navbar a:first-child"
                    ).first

                if logo.is_visible():
                    logo.click()
                    print("      ⏳ Waiting for Home page to load (5-10s)...")
                    time.sleep(7)
                    page.wait_for_selector("text=Process Blueprints", timeout=10000)
                    print("      ✅ Navigated to Home page")
                else:
                    raise Exception("Cannot find The Brick logo to navigate home")

            time.sleep(0.5)

            for opt in options:
                is_uncheck = opt.startswith("-")
                opt_name = opt.lstrip("-").strip() if is_uncheck else opt.strip()
                opt_lower = opt_name.lower()

                if opt_lower in ("toggle all", "toogle all", "select all", "check all"):
                    print("      🔲 Clicking Toggle All checkbox...")
                    try:
                        toggle_label = (
                            page.locator("label")
                            .filter(
                                has_text=re.compile(
                                    r"toggle\s*all|select\s*all|check\s*all",
                                    re.IGNORECASE,
                                )
                            )
                            .first
                        )
                        if toggle_label.is_visible():
                            toggle_chk = toggle_label.locator(
                                "input[type='checkbox']"
                            ).first
                            if not toggle_chk.is_visible():
                                id_v = toggle_label.get_attribute("for")
                                if id_v:
                                    toggle_chk = page.locator(f"#{id_v}")
                            if toggle_chk.is_visible():
                                if is_uncheck:
                                    if toggle_chk.is_checked():
                                        toggle_chk.uncheck()
                                        print("         ✅ Unchecked Toggle All")
                                    else:
                                        print(
                                            "         ✅ Already unchecked: Toggle All"
                                        )
                                else:
                                    if not toggle_chk.is_checked():
                                        toggle_chk.check()
                                        print("         ✅ Checked Toggle All")
                                    else:
                                        print("         ✅ Already checked: Toggle All")
                                time.sleep(1)
                                continue

                        toggle_btn = (
                            page.locator("button, a, span")
                            .filter(
                                has_text=re.compile(
                                    r"toggle\s*all|select\s*all", re.IGNORECASE
                                )
                            )
                            .first
                        )
                        if toggle_btn.is_visible():
                            toggle_btn.click()
                            print("         ✅ Clicked Toggle All button")
                            time.sleep(1)
                            continue
                        print("         ⚠️ Toggle All not found")
                    except Exception as e:
                        print(f"         ⚠️ Toggle All error: {e}")
                    continue

                if is_uncheck:
                    print(f"      ☐ Unchecking option: '{opt_name}'")
                else:
                    print(f"      🔲 Ticking option: '{opt_name}'")

                lbl = (
                    page.locator("label")
                    .filter(has_text=re.compile(re.escape(opt_name), re.IGNORECASE))
                    .first
                )
                if lbl.is_visible():
                    chk = lbl.locator("input[type='checkbox']").first
                    if not chk.is_visible():
                        id_v = lbl.get_attribute("for")
                        if id_v:
                            chk = page.locator(f"#{id_v}")
                    if chk.is_visible():
                        if is_uncheck:
                            if chk.is_checked():
                                chk.uncheck()
                                print(f"         ✅ Unchecked: '{opt_name}'")
                            else:
                                print(f"         ✅ Already unchecked: '{opt_name}'")
                        else:
                            if not chk.is_checked():
                                chk.check()
                                print(f"         ✅ Ticked: '{opt_name}'")
                            else:
                                print(f"         ✅ Already ticked: '{opt_name}'")
                    else:
                        print(f"         ⚠️ Checkbox not visible for: '{opt_name}'")
                else:
                    try:
                        text_el = page.locator(f"text='{opt_name}'").first
                        if text_el.is_visible():
                            chk_nearby = text_el.locator(
                                "xpath=preceding-sibling::input[@type='checkbox'] | following-sibling::input[@type='checkbox'] | ../input[@type='checkbox']"
                            ).first
                            if chk_nearby.is_visible():
                                if is_uncheck:
                                    if chk_nearby.is_checked():
                                        chk_nearby.uncheck()
                                        print(
                                            f"         ✅ Unchecked via nearby: '{opt_name}'"
                                        )
                                    else:
                                        print(
                                            f"         ✅ Already unchecked: '{opt_name}'"
                                        )
                                else:
                                    if not chk_nearby.is_checked():
                                        chk_nearby.check()
                                        print(
                                            f"         ✅ Ticked via nearby: '{opt_name}'"
                                        )
                                    else:
                                        print(
                                            f"         ✅ Already checked: '{opt_name}'"
                                        )
                            else:
                                print(
                                    f"         ⚠️ Cannot {'uncheck' if is_uncheck else 'tick'}: '{opt_name}'"
                                )
                        else:
                            print(f"         ⚠️ Label not found: '{opt_name}'")
                    except Exception as e:
                        print(f"         ⚠️ Strategy 2 failed for '{opt_name}': {e}")

            if options:
                print("      🖱 Clicking Process button...")
                btn = page.locator("button:has-text('Process')").first
                if btn.is_visible():
                    btn.click()
                    print("      ✅ Clicked Process button")
                    time.sleep(2)
                else:
                    raise Exception("Process button not found or not visible")
            else:
                print("      ℹ️ No options selected — navigated home only, skipping Process button")

        except Exception as e:
            print(f"   ❌ Process Deployment Error: {e}")
            raise e

