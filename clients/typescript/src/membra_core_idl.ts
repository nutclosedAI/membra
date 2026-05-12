/**
 * Placeholder IDL types for MEMBRA Core.
 * After `anchor build`, replace this with the generated IDL from
 * `target/types/membra_core.ts`.
 */

import { Idl } from "@coral-xyz/anchor";

export interface MembraCore extends Idl {
  version: "0.1.0";
  name: "membra_core";
  instructions: any[];
  accounts: any[];
  types: any[];
  events: any[];
  errors: any[];
}

// Minimal type stub for compilation
export type MembraCoreProgram = any;
