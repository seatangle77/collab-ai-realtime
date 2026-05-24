package com.collabai.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

public class JPushMessageReceiver extends cn.jpush.android.service.JPushMessageReceiver {
    private static final String TAG = "JPushReceiver";
    private static final String PREFS_NAME = "jpush_device";
    private static final String KEY_REGISTRATION_ID = "registration_id";

    @Override
    public void onRegister(Context context, String registrationId) {
        super.onRegister(context, registrationId);
        Log.i(TAG, "JPush registrationId=" + registrationId);
        if (registrationId != null && !registrationId.trim().isEmpty()) {
            SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
            prefs.edit().putString(KEY_REGISTRATION_ID, registrationId.trim()).apply();
        }
    }
}
