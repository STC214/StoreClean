package android.view;

/** Minimal host-test View state; not Android rendering and never shipped. */
public class View {
    public static final int GONE = 8;
    public boolean enabled = true;
    public boolean clickable = true;
    public int visibility;
    public OnClickListener listener = view -> {};

    public interface OnClickListener {
        void onClick(View view);
    }

    public void setOnClickListener(OnClickListener value) {
        listener = value;
    }

    public void setClickable(boolean value) {
        clickable = value;
    }

    public void setEnabled(boolean value) {
        enabled = value;
    }

    public void setVisibility(int value) {
        visibility = value;
    }
}
