package com.collabai.app;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(JPushDevicePlugin.class);
        super.onCreate(savedInstanceState);
    }
}
