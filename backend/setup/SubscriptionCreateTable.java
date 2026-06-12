// Copyright 2012-2015 Amazon.com, Inc. or its affiliates. All Rights Reserved.
// Licensed under the Apache License, Version 2.0.

package com.amazonaws.samples;

import com.amazonaws.auth.profile.ProfileCredentialsProvider;
import com.amazonaws.regions.Regions;
import com.amazonaws.services.dynamodbv2.AmazonDynamoDB;
import com.amazonaws.services.dynamodbv2.AmazonDynamoDBClientBuilder;
import com.amazonaws.services.dynamodbv2.document.DynamoDB;
import com.amazonaws.services.dynamodbv2.document.Table;
import com.amazonaws.services.dynamodbv2.model.*;

public class SubscriptionCreateTable {

    public static void main(String[] args) throws Exception {

        AmazonDynamoDB client = AmazonDynamoDBClientBuilder.standard().withRegion(Regions.AP_SOUTHEAST_2).withCredentials().build();

        DynamoDB dynamoDB = new DynamoDB(client);

        String tableName = "Subscription";

        try {
            System.out.println("Attempting to create table; please wait...");

            CreateTableRequest request = new CreateTableRequest()
                    .withTableName(tableName)
                    .withKeySchema(
                            new KeySchemaElement("emailId", KeyType.HASH), // Partition key
                            new KeySchemaElement("title_album", KeyType.RANGE) // Sort key
                    )
                    .withAttributeDefinitions(
                            new AttributeDefinition("emailId", ScalarAttributeType.S),
                            new AttributeDefinition("title_album", ScalarAttributeType.S)

                    ).withBillingMode(BillingMode.PAY_PER_REQUEST);


            Table table = dynamoDB.createTable(request);
            table.waitForActive();
            System.out.println("Success.  Table status: " + table.getDescription().getTableStatus());

        } catch (Exception e) {
            System.err.println("Unable to create table: ");
            System.err.println(e.getMessage());
        }

    }
}