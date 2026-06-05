"use client";

import { Save, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Page } from "@/components/layout/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const sizingModes = ["SAME_QTY", "MULTIPLIER", "FIXED_QTY", "PERCENT_CAPITAL"];
const sides = ["B", "S"];

export default function RiskSettingsPage() {
  const [sizing, setSizing] = useState("SAME_QTY");
  const [allowedSides, setAllowedSides] = useState(["B", "S"]);

  return (
    <Page title="Risk Settings">
      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle>Sizing</CardTitle>
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="flex flex-wrap gap-2">
              {sizingModes.map((mode) => (
                <Button key={mode} variant={sizing === mode ? "default" : "outline"} onClick={() => setSizing(mode)}>
                  {mode}
                </Button>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Input placeholder="Multiplier" />
              <Input placeholder="Fixed quantity" />
              <Input placeholder="Capital percent" />
              <Input placeholder="Max quantity" />
              <Input placeholder="Max order value" />
              <Input placeholder="Max slippage percent" />
            </div>
            <Button onClick={() => toast.success("Risk settings saved")}>
              <Save className="h-4 w-4" />
              Save
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Filters</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <Input placeholder="Allowed symbols" />
            <Input placeholder="Blocked symbols" />
            <div className="flex gap-2">
              {sides.map((side) => (
                <Button
                  key={side}
                  variant={allowedSides.includes(side) ? "default" : "outline"}
                  onClick={() =>
                    setAllowedSides((current) =>
                      current.includes(side) ? current.filter((item) => item !== side) : [...current, side]
                    )
                  }
                >
                  {side}
                </Button>
              ))}
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4" />
              Auto square-off
            </label>
          </CardContent>
        </Card>
      </div>
    </Page>
  );
}
