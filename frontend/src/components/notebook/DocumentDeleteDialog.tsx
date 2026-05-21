"use client";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { useT } from "@/hooks/useT";

type Props = {
  filename: string | null;
  open: boolean;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function DocumentDeleteDialog({
  filename,
  open,
  pending,
  onConfirm,
  onCancel,
}: Props) {
  const { t } = useT();
  return (
    <ConfirmDialog
      open={open}
      pending={pending}
      title={t("notebook.deleteDocumentTitle")}
      confirmLabel={t("notebook.deleteDocumentConfirm")}
      cancelLabel={t("common.cancel")}
      onConfirm={onConfirm}
      onCancel={onCancel}
      description={t("notebook.deleteDocumentBody", { filename: filename ?? "" })}
    />
  );
}
