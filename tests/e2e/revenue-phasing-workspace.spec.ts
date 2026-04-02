import { expect, test, type Page } from "@playwright/test";

test.describe.configure({ mode: "serial" });

function parsePhasingInputTestId(testId: string) {
  const match = /^phasing-input-(.+)-(\d{4}-\d{2})$/.exec(testId);
  if (!match) {
    throw new Error(`Unexpected phasing input test id: ${testId}`);
  }
  return {
    rowKey: match[1]!,
    month: match[2]!,
  };
}

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@quotes4.dev");
  await page.getByLabel("Password").fill("quotes4-admin-password");
  await Promise.all([
    page.waitForURL(/\/dashboard$/, { timeout: 10_000 }),
    page.getByRole("button", { name: "Sign in" }).click(),
  ]);
}

async function openPhasingWorkspace(page: Page) {
  await page.goto("/projects/phasing?rowMode=project&scenarioKey=base");
  const firstInput = page.locator('[data-testid^="phasing-input-"]').first();
  await expect(firstInput).toBeVisible();
}

test("persists a shared phasing draft across reload and supports discard", async ({ page }) => {
  await login(page);
  await openPhasingWorkspace(page);

  const firstInput = page.locator('[data-testid^="phasing-input-"]').first();
  const inputTestId = await firstInput.getAttribute("data-testid");
  expect(inputTestId).toBeTruthy();

  const originalValue = await firstInput.inputValue();
  const updatedValue = originalValue === "1234" ? "2345" : "1234";

  await firstInput.click();
  await firstInput.fill(updatedValue);
  await page.waitForTimeout(500);

  await page.reload();

  const reloadedInput = page.getByTestId(inputTestId!);
  await expect(reloadedInput).toHaveValue(updatedValue);
  await expect(page.getByText("Shared draft", { exact: false }).first()).toBeVisible();

  await page.getByRole("button", { name: "Cancel changes" }).click();
  await expect(page.getByTestId(inputTestId!)).toHaveValue(originalValue, { timeout: 10_000 });
  await page.reload();
  await expect(page.getByTestId(inputTestId!)).toHaveValue(originalValue);
});

test("supports rectangular paste in the browser and row-level undo", async ({ page }) => {
  await login(page);
  await openPhasingWorkspace(page);

  const inputTestIds = await page
    .locator('[data-testid^="phasing-input-"]')
    .evaluateAll((elements) =>
      elements
        .map((element) => element.getAttribute("data-testid"))
        .filter((value): value is string => Boolean(value)),
    );
  const parsedInputs = inputTestIds.map((testId) => parsePhasingInputTestId(testId));
  const rowKeys = Array.from(new Set(parsedInputs.map((item) => item.rowKey)));
  const months = Array.from(new Set(parsedInputs.map((item) => item.month)));

  expect(rowKeys.length).toBeGreaterThanOrEqual(2);
  expect(months.length).toBeGreaterThanOrEqual(2);

  const firstRowKey = rowKeys[0]!;
  const secondRowKey = rowKeys[1]!;
  const firstMonth = months[0]!;
  const secondMonth = months[1]!;
  const firstCellId = `phasing-input-${firstRowKey}-${firstMonth}`;
  const firstRowSecondMonthId = `phasing-input-${firstRowKey}-${secondMonth}`;
  const secondRowFirstMonthId = `phasing-input-${secondRowKey}-${firstMonth}`;
  const secondCellId = `phasing-input-${secondRowKey}-${secondMonth}`;

  const firstCell = page.getByTestId(firstCellId);
  const firstRowSecondMonthCell = page.getByTestId(firstRowSecondMonthId);
  const secondRowFirstMonthCell = page.getByTestId(secondRowFirstMonthId);
  const secondCell = page.getByTestId(secondCellId);
  const originalValues = await Promise.all([
    firstCell.inputValue(),
    firstRowSecondMonthCell.inputValue(),
    secondRowFirstMonthCell.inputValue(),
    secondCell.inputValue(),
  ]);

  await firstCell.click();
  await page.keyboard.down("Shift");
  await secondCell.click();
  await page.keyboard.up("Shift");
  await expect(page.getByText(/^2 rows × 2 months/i)).toBeVisible();
  await page.evaluate(
    ({ testId, text }) => {
      const selector = `[data-testid="${CSS.escape(testId)}"]`;
      const target = document.querySelector(selector);
      if (!(target instanceof HTMLInputElement)) {
        throw new Error(`Expected phasing input for ${testId}`);
      }
      const pasteEvent = new Event("paste", { bubbles: true });
      Object.defineProperty(pasteEvent, "clipboardData", {
        value: {
          getData: () => text,
        },
      });
      target.dispatchEvent(pasteEvent);
    },
    { testId: firstCellId, text: "1111\t2222\n3333\t4444" },
  );

  await expect(firstCell).toHaveValue("1111");
  await expect(firstRowSecondMonthCell).toHaveValue("2222");
  await expect(secondRowFirstMonthCell).toHaveValue("3333");
  await expect(secondCell).toHaveValue("4444");

  const undoButton = page.getByTestId("phasing-undo");
  await expect(undoButton).toBeEnabled();
  await undoButton.click();

  await expect(firstCell).toHaveValue("1111");
  await expect(firstRowSecondMonthCell).toHaveValue("2222");
  await expect(secondRowFirstMonthCell).toHaveValue(originalValues[2]!);
  await expect(secondCell).toHaveValue(originalValues[3]!);

  await firstCell.click();
  await page.getByRole("button", { name: "Cancel changes" }).click();
  await expect(firstCell).toHaveValue(originalValues[0]!, { timeout: 10_000 });
  await expect(firstRowSecondMonthCell).toHaveValue(originalValues[1]!);

  await secondRowFirstMonthCell.click();
  await page.getByRole("button", { name: "Cancel changes" }).click();
  await expect(secondRowFirstMonthCell).toHaveValue(originalValues[2]!, { timeout: 10_000 });
  await expect(secondCell).toHaveValue(originalValues[3]!);
});
