package com.collabai.app;

import android.content.Context;
import android.content.SharedPreferences;

import cn.jpush.android.api.JPushInterface;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "JPushDevice")
public class JPushDevicePlugin extends Plugin {
    private static final String PREFS_NAME = "jpush_device";
    private static final String KEY_REGISTRATION_ID = "registration_id";

    @PluginMethod
    public void getRegistrationId(PluginCall call) {
        String registrationId = JPushInterface.getRegistrationID(getContext());
        if (registrationId == null || registrationId.trim().isEmpty()) {
            SharedPreferences prefs = getContext().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
            registrationId = prefs.getString(KEY_REGISTRATION_ID, "");
        }
        JSObject result = new JSObject();
        result.put("deviceToken", registrationId == null ? "" : registrationId.trim());
        call.resolve(result);
    }
}
