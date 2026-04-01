package com.collabai.app;

import android.app.Application;
import android.util.Log;
import cn.jpush.android.api.JPushInterface;

public class MyApplication extends Application {
    private static final String TAG = "JPushInit";

    @Override
    public void onCreate() {
        super.onCreate();
        // Release 包建议关闭 debug，避免日志泄漏。
        JPushInterface.setDebugMode(BuildConfig.DEBUG);
        JPushInterface.init(this);
        Log.i(TAG, "JPush initialized");
    }
}
